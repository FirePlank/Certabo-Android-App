import chess.pgn
import chess
import io

pgns = """""".split("\n\n\n")

import random

fens = {}

games = [chess.pgn.read_game(io.StringIO(game)) for game in pgns]
board = chess.Board()
game = games[0]
node = game.next()
while node:
    print(node.move)
    board.push(node.move)

    if len(node.variations) > 1:
        # get all possible moves for all variations
        moves = []
        for idx, variation in enumerate(node.variations):
            moves.append((idx, variation.move))
        # pick a random move
        move = random.choice(moves)
        if move[0] == 0:
            print("mainline", move[1])
        else:
            print("variation", move[1])
        node = node.variations[move[0]]
        board.push(node.move)
        
    node = node.next()
    
print(board)

# go through mainline until a variation is found, in which case start following that instead until it ends
