#!/bin/bash
# install_cron.sh
# Adds daily_update.py to crontab (runs weekdays at 7:00 AM)
# Run once: bash install_cron.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/daily_update.py"
LOG="$SCRIPT_DIR/daily_update.log"
PYTHON="$(which python3)"

# Verify the script exists
if [ ! -f "$SCRIPT" ]; then
    echo "ERROR: $SCRIPT not found"
    exit 1
fi

# Make it executable
chmod +x "$SCRIPT"

# The cron line: weekdays at 7:00 AM
CRON_LINE="0 7 * * 1-5 $PYTHON $SCRIPT >> $LOG 2>&1"

# Check if it's already installed
if crontab -l 2>/dev/null | grep -qF "$SCRIPT"; then
    echo "Crontab entry already exists:"
    crontab -l | grep "$SCRIPT"
    echo ""
    echo "To remove it, run: crontab -e and delete the line."
    exit 0
fi

# Add to crontab
( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -

echo ""
echo "Crontab installed successfully!"
echo ""
echo "   Schedule : Weekdays at 7:00 AM"
echo "   Script   : $SCRIPT"
echo "   Log      : $LOG"
echo "   Python   : $PYTHON"
echo ""
echo "Current crontab:"
crontab -l
echo ""
echo "To test immediately, run:"
echo "   python3 $SCRIPT"
echo ""
echo "To view the log:"
echo "   tail -f $LOG"
echo ""
echo "To remove this cron job:"
echo "   crontab -e   (then delete the daily_update line)"
