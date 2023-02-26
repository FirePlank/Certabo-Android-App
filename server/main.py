import logging
from flask import Flask, request
import chess.engine
import chess
import os

app = Flask(__name__)

# initialize the engine when the server starts up, please change this to your own engine path
engines = os.listdir("engines")
engines = [engine for engine in engines if engine.endswith(".exe")]
if len(engines) == 0:
    raise Exception("No engines found in engines folder")

engine = chess.engine.SimpleEngine.popen_uci(f"engines/{engines[0]}")


# define a custom logging filter that silences logs for the /move endpoint since it can get quite noisy
class SilenceMoveEndpoint(logging.Filter):
    def filter(self, record):
        try:
            return "/move" not in record.args[0]
        except:
            return True
    
# set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('werkzeug')
logger.addFilter(SilenceMoveEndpoint())


@app.route('/')
def index():
    return 'Server is running'

@app.route('/move')
def get_best_move():
    fen = request.args.get('fen')
    if fen is None:
        return "Please enter a FEN"
    board = chess.Board(fen)
    try:
        result = engine.play(board, chess.engine.Limit(time=0.1))
        return result.move.uci()
    except:
        return "Invalid FEN"
    
@app.route('/engines')
def get_engines():
    # list all engines in the engines folder
    engines = os.listdir("engines")
    # only include files that end with .exe
    engines = [engine for engine in engines if engine.endswith(".exe")]
    return str(engines)

@app.route('/set_engine')
def set_engine():
    # switch to a different engine
    global engine
    name = request.args.get('name')
    if name is None:
        return "Please enter a name"
    
    try:
        engine = chess.engine.SimpleEngine.popen_uci(f"engines/{name}")
    except FileNotFoundError:
        return "Engine not found"
    
    return "Engine set"

if __name__ == '__main__':
    port = 5000
    app.run(port=port, host='0.0.0.0')