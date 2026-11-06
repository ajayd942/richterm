# Color one Kafka record at a time. Keep payload strings intact, including
# escaped quotes, and flush each record before waiting for the next one.
_option3_kafka_events() {
  command awk '
    BEGIN {
      esc=sprintf("%c",27); off=esc "[0m"; cyan=esc "[1;96m"; lime=esc "[92m"
      pink=esc "[95m"; gold=esc "[93m"; dim=esc "[90m"
    }
    function json(s,    token,tail,color) {
      while (match(s,/"([^"\\]|\\.)*"|-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?|true|false|null/)) {
        printf "%s", substr(s,1,RSTART-1)
        token=substr(s,RSTART,RLENGTH); tail=substr(s,RSTART+RLENGTH)
        color=(substr(token,1,1)=="\"" ? (tail ~ /^[[:space:]]*:/ ? cyan : gold) : pink)
        printf "%s%s%s",color,token,off; s=tail
      }
      printf "%s",s
    }
    {
      # Kafka default formatter uses tabs between metadata, key, and value.
      count=split($0,field,"\t"); value=field[count]
      if ($0 !~ /[[:cntrl:]]/ || $0 ~ /\t/) {
        if (value ~ /^[ ]*[{\[]/ && $0 !~ /\033/) {
          if(count>1) {
            printf "%s▌%s ",cyan,off
            for(i=1;i<count;i++) {
              if(i>1) printf "%s  ·  %s",dim,off
              printf "%s%s%s",(field[i] ~ /^Partition:/ ? cyan : lime),field[i],off
            }
            printf "\n  "
          }
          json(value); printf "\n"; fflush(); next
        }
      }
      print; fflush()
    }'
}
