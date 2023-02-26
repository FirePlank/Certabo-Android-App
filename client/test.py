import chess.pgn
import chess
import io
import time
import berserk

board = chess.Board()
board.push_san("e4")
board.push_san("e5")
board.push_san("Qh5")
board.push_san("Nc6")
board.push_san("Bc4")
board.push_san("Nf6")
board.push_san("Qxf7#")

# print(board)
# get pgn
game = chess.pgn.Game()
game.headers["Event"] = "Casual Game"
game.headers["Site"] = "Certabo Board Game"
game.headers["Round"] = "1"
game.headers["Date"] = time.strftime("%Y.%m.%d")
game.headers["White"] = "White"
game.headers["Black"] = "Black"
game.headers["Result"] = board.result()

# go through board moves starting from the beginning
node = game
for move in board.move_stack:
    node = node.add_variation(move)

pgn = game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=False))
print(pgn)

# send post request to lichess.org/api/import
response = berserk.TokenSession("").post("https://lichess.org/api/import", data={"pgn": pgn})
# convert to json and get "url" key
print(response.json()["url"])

# pgns = """""".split("\n\n\n")

# import random

# fens = {}

# games = [chess.pgn.read_game(io.StringIO(game)) for game in pgns]
# board = chess.Board()
# game = games[0]
# node = game.next()
# while node:
#     print(node.move)
#     board.push(node.move)

#     if len(node.variations) > 1:
#         # get all possible moves for all variations
#         moves = []
#         for idx, variation in enumerate(node.variations):
#             moves.append((idx, variation.move))
#         # pick a random move
#         move = random.choice(moves)
#         if move[0] == 0:
#             print("mainline", move[1])
#         else:
#             print("variation", move[1])
#         node = node.variations[move[0]]
#         board.push(node.move)
        
#     node = node.next()
    
# print(board)

# # go through mainline until a variation is found, in which case start following that instead until it ends
