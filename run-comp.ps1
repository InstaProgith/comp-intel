param(
    [Parameter(Mandatory = $true)]
    [string]$RedfinUrl
)

# Go to project root
Set-Location "C:\Users\navid\comp-intel"

# Activate virtual env
.\.venv\Scripts\Activate.ps1

# Run orchestrator
python .\app\orchestrator.py --url "$RedfinUrl"
