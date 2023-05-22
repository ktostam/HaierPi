from flask import Flask, render_template, Response
import subprocess

app = Flask(__name__)

def stream_journal_entries():
    # Execute the journalctl command with the '-f' flag to follow new entries
    proc = subprocess.Popen(['journalctl', '-f', '-t', 'HaierPi', '-p','info'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    # Read and yield each line of the journal output
    for line in iter(proc.stdout.readline, ''):
        yield 'data: {}\n\n'.format(line.strip())

@app.route('/')
def index():
    return render_template('weblog.html')

@app.route('/stream')
def stream():
    return Response(stream_journal_entries(), mimetype='text/event-stream', headers={"Access-Control-Allow-Origin": "*"} )

if __name__ == '__main__':
    app.run(host="0.0.0.0")