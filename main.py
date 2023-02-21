from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

import requests
import chess.pgn
import chess
import io
import random


messages = ["Error: Please enter a study ID", "Error: Study does not exist or is private", "Success!"]

class OpeningExplorerApp(App):

    def build(self):
        # Set window properties
        self.title = "Certabo Opening Explorer"
        self.icon = 'assets/icon.png'
        self.window = GridLayout(padding=20, spacing=10)

        # Set background color to white
        self.window.cols = 1
        self.window.size_hint = (0.8, 0.4)
        self.window.pos_hint = {'center_x': 0.5, 'center_y': 0.7}

        # Image widget lichess.png
        self.window.add_widget(Image(source='assets/lichess.png', size_hint=(1, None), height=150))

        # Label widget
        self.window.add_widget(Label(text='Enter lichess study ID (e.g LguNS44c)', font_size=30, size_hint=(1, None), height=50))

        # Text input widget
        self.text_input = TextInput(multiline=False, size_hint=(1, None), height=75, 
                               background_color=(1, 1, 1, 1),  # Set white background
                               padding=[20, 10])
        self.window.add_widget(self.text_input)

        # Button widget
        submit_button = Button(text='Submit', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10])
        submit_button.bind(on_press=self.callback)
        self.window.add_widget(submit_button)

        return self.window

    def callback(self, instance):
        # if text input is empty, return error text
        if self.text_input.text == '':
            # remove exisiting label if it exists
            if self.window.children[0].text in messages:
                self.window.remove_widget(self.window.children[0])
            
            self.window.add_widget(Label(text=messages[0], font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))

        else:
            # remove exisiting label if it exists
            if self.window.children[0].text in messages:
                self.window.remove_widget(self.window.children[0])
            
            # fetch study pgn from lichess
            study_id = self.text_input.text.strip()
            url = f'https://lichess.org/api/study/{study_id}.pgn'

            # check if study exists
            try:
                r = requests.get(url)
                r.raise_for_status()
            except requests.exceptions.HTTPError as err:
                # check if error label already exists
                if self.window.children[0].text == messages[1]:
                    return
                else:
                    # add error label with red text
                    self.window.add_widget(Label(text=messages[1], font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                return
            
            # if study exists, remove error label if it exists
            if self.window.children[0].text == messages[1]:
                self.window.remove_widget(self.window.children[0])

            # get pgn from response
            pgns = r.text.split('\n\n')
            games = [chess.pgn.read_game(io.StringIO(game)) for game in pgns]
            board = chess.Board()
            game = random.choice(games)

            # add success label with green text
            self.window.add_widget(Label(text=messages[2], font_size=30, size_hint=(1, None), height=50, color=(0, 1, 0, 1)))

            node = game.next()
            while node:
                # print(node.move)
                board.push(node.move)

                if len(node.variations) > 1:
                    # get all possible moves for all variations
                    moves = []
                    for idx, variation in enumerate(node.variations):
                        moves.append((idx, variation.move))

                    # pick a random move
                    move = random.choice(moves)
                    node = node.variations[move[0]]
                    board.push(node.move)
                    
                node = node.next()
                
            print(board)


if __name__ == '__main__':
    OpeningExplorerApp().run()
