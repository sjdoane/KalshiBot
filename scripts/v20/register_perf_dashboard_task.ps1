# Register (or update) the KalshiPerfDashboard scheduled task: regenerate the
# v1 performance dashboard + CSV every 20 minutes. Creates a USER-CONTEXT task
# via schtasks, which works WITHOUT admin (Register-ScheduledTask needs
# elevation in this environment). Read-only; safe alongside the live bot.
#
# Re-run to update. Remove with:
#   schtasks /Delete /TN "KalshiPerfDashboard" /F
# Inspect with:
#   schtasks /Query /TN "KalshiPerfDashboard" /V /FO LIST
#
# The --% stop-parsing token passes the rest verbatim so the space in the path
# and the inner \" quotes reach schtasks intact (a plain variable gets mangled).
schtasks --% /Create /TN "KalshiPerfDashboard" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"C:\Users\SamJD\OneDrive\Desktop\AI Projects\Project Kalshi\scripts\v20\run_perf_dashboard.ps1\"" /SC MINUTE /MO 20 /F
