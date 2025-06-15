# Add all changes
git add .

# Use the first argument as the commit message, or "bug fix" if no argument is provided
if [ -z "$1" ]; then
  git commit -m "bug fix"
else
  git commit -m "$1"
fi

# Push the changes
git push
