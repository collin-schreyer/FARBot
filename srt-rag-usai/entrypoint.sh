#!/bin/bash
set -e

echo "=== SRT-RAG-USAI Container Starting ==="
echo "Date: $(date)"
echo "RUN_MODE: ${RUN_MODE:-daily}"

# Write environment variables to a file so cron can access them
echo "export PATH=/usr/local/bin:/usr/bin:/bin" > /app/env.sh
env | grep -E "^(USAI_|SAM_|DATABASE_URL|SECTION_508|VCAP_|PORT)" >> /app/env.sh
sed -i '/^export /! s/^/export /' /app/env.sh

# Set up cron job: run daily at 6 AM UTC
echo "0 6 * * * . /app/env.sh && cd /app && python main.py --daily --attachments-dir /app/attachments --csv-output /app/output/daily_\$(date +\%Y\%m\%d).csv >> /app/output/cron.log 2>&1" > /etc/cron.d/srt-rag
chmod 0644 /etc/cron.d/srt-rag
crontab /etc/cron.d/srt-rag

# Start cron daemon
cron
echo "Cron daemon started (daily at 06:00 UTC)"

# Run initial pipeline in the BACKGROUND so health server can start immediately
if [ "${RUN_MODE}" = "daily" ]; then
    echo "=== Running initial daily pipeline (background) ==="
    (python main.py --daily \
        --attachments-dir /app/attachments \
        --csv-output /app/output/daily_$(date +%Y%m%d).csv \
        ${SCRAPE_FROM_DATE:+--from-date $SCRAPE_FROM_DATE} \
        ${SCRAPE_TO_DATE:+--to-date $SCRAPE_TO_DATE} \
        ${SCRAPE_LIMIT:+--limit $SCRAPE_LIMIT} \
        2>&1 | tee /app/output/run.log) &
    echo "Pipeline started in background (PID: $!)"
fi

# Health check server in foreground — keeps the container alive for cloud.gov
echo "=== Starting health check server on port ${PORT:-8080} ==="
python -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, os, glob

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'service': 'srt-rag-usai'}).encode())
        elif self.path == '/output':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            log = ''
            for f in ['/app/output/run.log', '/app/output/cron.log']:
                if os.path.exists(f):
                    with open(f, 'r') as fh:
                        log += f'=== {f} ===\n' + fh.read() + '\n'
            self.wfile.write((log or 'No output yet').encode())
        elif self.path == '/csv':
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv')
            self.end_headers()
            csvs = sorted(glob.glob('/app/output/*.csv'))
            if csvs:
                with open(csvs[-1], 'r') as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b'No CSV yet')
        elif self.path == '/attachments':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            lines = []
            att = '/app/attachments'
            if os.path.isdir(att):
                for d in sorted(os.listdir(att)):
                    full = os.path.join(att, d)
                    if os.path.isdir(full):
                        files = os.listdir(full)
                        lines.append(f'{d}/ ({len(files)} files)')
                        for f in sorted(files)[:10]:
                            lines.append(f'  {f}')
            self.wfile.write(('\n'.join(lines) or 'No attachments').encode())
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''<h2>srt-rag-usai</h2>
<a href=\"/health\">health</a> |
<a href=\"/output\">pipeline log</a> |
<a href=\"/csv\">csv output</a> |
<a href=\"/attachments\">downloaded attachments</a>''')
    def log_message(self, format, *args):
        pass

port = int(os.environ.get('PORT', 8080))
print(f'Health server listening on port {port}')
HTTPServer(('0.0.0.0', port), Handler).serve_forever()
"
