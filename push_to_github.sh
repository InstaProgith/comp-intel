#!/bin/bash
# Simple script to help push changes to GitHub

echo "========================================="
echo "GitHub Push Helper"
echo "========================================="
echo ""

# Check if we're in the right directory
if [ ! -d ".git" ]; then
    echo "Error: Not in a git repository!"
    exit 1
fi

echo "Current branch:"
git branch --show-current
echo ""

echo "Current status:"
git status -sb
echo ""

echo "Commits ahead of origin:"
git log origin/main..HEAD --oneline
echo ""

echo "========================================="
echo "Ready to push to GitHub!"
echo "========================================="
echo ""
echo "Run this command:"
echo ""
echo "  git push origin main"
echo ""
echo "If you get authentication errors, set up authentication first:"
echo ""
echo "  gh auth login"
echo ""
echo "Then choose:"
echo "  - GitHub.com"
echo "  - HTTPS"
echo "  - Yes (authenticate Git)"
echo "  - Paste an authentication token"
echo ""
echo "Get your token from: https://github.com/settings/tokens"
echo "========================================="
