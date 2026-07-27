# vhs script (https://github.com/charmbracelet/vhs) — reproducible README
# demo. Record against a REAL repository and a REAL /work run; this tape
# only automates the terminal half. Regenerate with: vhs assets/demo.tape
Output assets/demo.gif
Set FontSize 16
Set Width 1100
Set Height 620
Set Theme "Catppuccin Mocha"
Type "pipeline init" Enter Sleep 1s
Type "claude" Enter Sleep 2s
Type "/task add Add a request id header to every API response" Enter Sleep 3s
Type "/work T-$(date +%F)-add-a-request-id-header" Enter Sleep 6s
# ... gate 1: type "confirmed"; gate 2: read plan, type "approved";
# let review land, then:
Type "/status T-$(date +%F)-add-a-request-id-header" Enter Sleep 3s
Type "cat telemetry.jsonl | tail -1 | jq" Enter Sleep 4s
