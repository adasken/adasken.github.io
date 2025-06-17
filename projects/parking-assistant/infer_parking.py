import pandas as pd
from openai import OpenAI
import time
import json
import re

# Initialize OpenAI client with your API key
client = OpenAI(api_key="")  # Replace with your actual API key

def extract_json(text):
    """
    Try to parse the whole text as JSON, or extract the first JSON object from the text.
    """
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

def ask_gpt(row):
    prompt = f"""
You are an expert in interpreting parking meter rules for Brisbane.

IMPORTANT LOGIC:
- Always check RESTRICTIONS first. If a restriction applies at a given time, parking is NOT allowed, regardless of operational time or rates.
- If a restriction contains multiple time ranges (e.g. "CLEARWAY 7AM-9AM,4PM-7PM MON-FRI TOWAWAY"), you must treat ALL time ranges as restricted. Do not miss or skip any restricted period.
- If there are multiple restrictions in a single string (e.g. "LZ 5AM-3PM M-F, BZ 3PM-7PM M-F & 12:30AM-6AM S-S"), each restriction must be parsed and applied to the correct time range and days.
- If a restriction uses abbreviations, expand them: C/W or C/WAY = CLEARWAY, LZ = LOADING ZONE, BZ = BUS ZONE. All are restricted (no parking) during their times.
- If a restriction says "ALL OTHER TIMES", it means that outside the specified operational times, the restriction applies (e.g. "TAXI ZONE ALL OTHER TIMES" means you cannot park outside the operational times).
- Only if there is NO restriction at a given time, check OPERATIONAL_DAY and OPERATIONAL_TIME to see if paid parking applies.
- If it is not an operational day, but the logic below says it should be free (e.g. MON-FRI on weekends), then it is free.
- If it is an operational day, check if the time is within operational hours. If not, it is free.
- If it is within operational hours, check the rate. If the rate is 0 or empty, it is free. Otherwise, it is paid and show the fee.

Restriction types: TOWAWAY, BUS ZONE, CLEARWAY, NO STOPPING, LOADING ZONE, PASSENGER LOADING ZONE, M/C PARKING ONLY, TAXI ZONE, C/W, C/WAY, LZ, BZ, JAZZ CLUB.
- C/W or C/WAY means CLEARWAY (restricted, no parking during its time).
- LZ means LOADING ZONE (restricted, no parking during its time).
- BZ means BUS ZONE (restricted, no parking during its time).

OPERATIONAL_DAY can be: MON-FRI, 7 DAYS, 6 DAYS, 5 DAYS, SAT-SUN, 7.

OPERATIONAL_TIME can be: 
- A single range (e.g. 7AM-7PM)
- Multiple ranges (e.g. 7AM-7PM,7PM-10PM(MON-FRI),7AM-7PM(SAT,SUN))
- Mixed with/without day notes (e.g. 9AM-4PM (MON-FRI), 7PM-10PM MON-FRI)

Special rules:
- If OPERATIONAL_DAY is MON-FRI or 5 DAYS, you can park for free all day on Saturday and Sunday.
- For restrictions like 'NO STOPPING 6AM-9AM,4PM-7PM MON-FRI', you cannot park from 6AM-9AM and 4PM-7PM on Monday to Friday.
- For restrictions like 'C/WAY & N/S 7AM-7PM MON-FRI TOWAWAY', it means Clearway and No Stopping from 7AM-7PM Monday to Friday.
- For a restriction like 'BUS ZONE 6AM-7PM MON-FRI TOWAWAY CLEARWAY C/WAY', if the current time is not in 6AM-7PM MON-FRI, then you can park there. To see if you need to pay, go to the next condition.
- For OPERATIONAL_DAY: 7 DAYS and OPERATIONAL_TIME: 7PM-10PM Mon-Fri, 7AM-7PM Sat-Sun, if the operational time is not in 7PM-10PM Mon-Fri or 7AM-7PM Sat-Sun, you can park for free. Otherwise, you need to pay.

ADDITIONAL INSTRUCTIONS:
- For each day, your output must start at 00:00 and cover the full 24 hours, with no gaps or overlaps. Every minute of the day must be accounted for as either Free, Paid, or Restricted (No parking).
- If a time range ends at, for example, 16:00, the next range must start at 16:00.
- Use 24-hour format (e.g., "00:00", "07:00", "16:00", "19:00", "23:59") for all 'from' and 'to' times for consistency.

WORKED EXAMPLES:

1. If RESTRICTIONS is 'LZ 5AM-3PM M-F, BZ 3PM-7PM M-F & 12:30AM-6AM S-S':
    - Loading zone (no parking) from 05:00-15:00 Monday to Friday
    - Bus zone (no parking) from 15:00-19:00 Monday to Friday
    - Bus zone (no parking) from 00:30-06:00 Saturday and Sunday
    - All other times: check operational time/rate or free

2. If RESTRICTIONS is 'TAXI ZONE ALL OTHER TIMES' and OPERATIONAL_TIME is '7AM-7PM,7PM-10PM(MON-FRI),7AM-7PM(SAT,SUN)':
    - You can park only during the operational times. All other times are taxi zone (no parking).

3. If RESTRICTIONS is 'C/W 7-11AM,2-7PM & LZ 11AM-2PM MON-SAT TOWAWAY':
    - Clearway (no parking) from 07:00-11:00 and 14:00-19:00 Monday to Saturday
    - Loading zone (no parking) from 11:00-14:00 Monday to Saturday

4. If RESTRICTIONS is 'C/WAY 7-9AM & 4-7PM M-F TOWAWAY':
    - Clearway (no parking) from 07:00-09:00 and 16:00-19:00 Monday to Friday

5. If RESTRICTIONS is 'CLEARWAY 7AM-9AM,4PM-7PM MON-FRI TOWAWAY' and OPERATIONAL_DAY is MON-FRI and OPERATIONAL_TIME is 9AM-16:00, and TAR_RATE_WEEKDAY is 6.15:
    - On Monday:
        - 00:00-07:00: Free
        - 07:00-09:00: No parking (restricted)
        - 09:00-16:00: Paid parking ($6.15)
        - 16:00-19:00: No parking (restricted)
        - 19:00-23:59: Free
    - On Saturday and Sunday: Free parking all day (00:00-23:59)

YOUR TASK:
Given the following parking meter info:
RESTRICTIONS: {row.get('RESTRICTIONS','')}
OPERATIONAL_DAY: {row.get('OPERATIONAL_DAY','')}
OPERATIONAL_TIME: {row.get('OPERATIONAL_TIME','')}
TAR_RATE_WEEKDAY: {row.get('TAR_RATE_WEEKDAY','')}
TAR_RATE_AH_WE: {row.get('TAR_RATE_AH_WE','')}

For each day of the week (Monday to Sunday), list the time ranges when parking is allowed, and for each range, specify if it is Free, Paid (and the fee if paid), or Restricted (No parking).
Format your answer as a valid JSON object with keys MON, TUE, WED, THU, FRI, SAT, SUN.
Each value should be a list of objects with 'from', 'to', 'type' (Free/Paid/No parking), and 'fee' (if paid).
Return ONLY the JSON object, no explanation or markdown.
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    text = response.choices[0].message.content
    # print(row.get('RESTRICTIONS', ''))
    # print("RAW RESPONSE:", text)  # For debugging
    print(row.get('METER_NO', ''), row.get('RESTRICTIONS', ''))
    return extract_json(text)

# Load the CSV
df = pd.read_csv('data/brisbane-parking-meters.csv')

# For demonstration, process only the first 3 rows (remove .head(3) to process all)
for idx, row in df.iterrows():
    gpt_result = ask_gpt(row)
    if gpt_result:
        for day in ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']:
            df.at[idx, f'{day}_PARKING'] = str(gpt_result.get(day, ''))
    else:
        for day in ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']:
            df.at[idx, f'{day}_PARKING'] = ''
    # time.sleep(1)  # To avoid rate limits

# Save to a new CSV
df.to_csv('data/brisbane-parking-meters_with_inferred_times.csv', index=False)
print("Done! Saved to data/brisbane-parking-meters_with_inferred_times.csv")