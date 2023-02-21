import chess.pgn
import chess
import io


games = [chess.pgn.read_game(io.StringIO(game)) for game in pgns]
print(games)
def get_random_move(position):
    print(position)

# board = chess.Board()
# # print(get_random_move(board))
# node = games[0].next()
# print(node.move)

# print(games[0].board())