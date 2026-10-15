# usage: step NAME "cmd" waitsec
step() { ./xbpad.exe send -r XBOX probe now 1 >/dev/null; ./xbpad.exe send -r XBOX $2 >/dev/null; sleep $3; r=$(./xbpad.exe send -r XBOX "probe?" | sed 's/  (call.*//'); ./xbpad.exe snap -r XBOX "results/cov/$1.png" >/dev/null; printf "%-16s %-22s %s\n" "$1" "$2" "$r"; }
