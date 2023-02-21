from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.storage.jsonstore import JsonStore

import requests
import chess.pgn
import chess
import io
import random
import berserk

messages = ["Error: Please enter a study ID", "Error: Study/Chapter does not exist or is private", "Success!"]

class MainScreen(Screen):
    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}

        # add title to top of screen
        self.layout.add_widget(Label(text='Certabo Chess App', font_size=50, size_hint=(1, None), height=100))

        self.layout.add_widget(Image(source='assets/lichess.png', size_hint=(1, None), height=150))

        # Add buttons for different options
        self.layout.add_widget(Button(text='Random Puzzle', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10]))

        self.layout.add_widget(Button(text='Opening Explorer', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10], on_press=self.opening_explorer))

        self.layout.add_widget(Button(text='Play Online', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10]))

        self.add_widget(self.layout)

    def opening_explorer(self, instance):
        self.manager.transition.direction = 'left'
        self.manager.current = 'opening_explorer'


class OpeningExplorerScreen(Screen):
    def __init__(self, **kwargs):
        super(OpeningExplorerScreen, self).__init__(**kwargs)
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}


        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.back))

        # Label widget
        self.layout.add_widget(Label(text='Enter lichess study/chapter ID (e.g mtuYBCxX or mtuYBCxX/H1rZIEMY)', font_size=20, size_hint=(1, None), height=50))

        # Text input widget with the previous id as default text if it exists
        self.text_input = TextInput(multiline=False, size_hint=(1, None), height=75, 
                                   background_color=(1, 1, 1, 1),  # Set white background
                                   padding=[20, 10])
    
        self.layout.add_widget(self.text_input)

        # dropdown menu for selecting previous ids
        store = JsonStore('data.json')
        self.dropdown = DropDown()
        if store.exists('study_ids'):
            for id in store.get('study_ids')['ids']:
                btn = Button(text=id, size_hint_y=None, height=44)
                btn.bind(on_release=lambda btn: self.dropdown.select(btn.text))
                self.dropdown.add_widget(btn)
            
        self.dropdown.bind(on_select=lambda instance, x: setattr(self.text_input, 'text', x))
        self.layout.add_widget(self.dropdown)


        # Button widget
        submit_button = Button(text='Submit', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10])
        submit_button.bind(on_press=self.callback)
        self.layout.add_widget(submit_button)

        # Create a horizontal BoxLayout
        hbox = BoxLayout(orientation='horizontal', size_hint=(1, None), height=50)

        # Add the checkbox widget to the BoxLayout
        self.checkbox = CheckBox(size_hint=(None, None), size=(50, 50), active=True)
        hbox.add_widget(self.checkbox)

        # Add the label widget to the BoxLayout
        label = Label(text='Include variations/sidelines', font_size=30, size_hint=(1, None), height=50)
        hbox.add_widget(label)

        # Add the BoxLayout to the GridLayout
        self.layout.add_widget(hbox)

        # Add the GridLayout to the screen
        self.add_widget(self.layout)

    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'main'

    def callback(self, instance):
        # if text input is empty, return error text
        if self.text_input.text == '':
            # check if it is a boxlayout
            if not isinstance(self.layout.children[0], BoxLayout):
                self.layout.remove_widget(self.layout.children[0])

            self.layout.add_widget(Label(text=messages[0], font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))

        else:
            # check if it is a boxlayout
            if not isinstance(self.layout.children[0], BoxLayout):
                self.layout.remove_widget(self.layout.children[0])

            # fetch study pgn from lichess
            study_id = self.text_input.text.strip()
            variations = "?variations=false" if not self.checkbox.active else ""

            # if study id contains a slash, it means they want a specific chapter
            if '/' in study_id:
                url = f'https://lichess.org/study/{study_id}.pgn{variations}'
            else:
                url = f'https://lichess.org/api/study/{study_id}.pgn{variations}'

            # check if study exists
            try:
                r = requests.get(url)
                r.raise_for_status()
            except requests.exceptions.HTTPError as err:
                # check if it is a boxlayout
                if not isinstance(self.layout.children[0], BoxLayout):
                    self.layout.remove_widget(self.layout.children[0])

                # add error label with red text
                self.layout.add_widget(Label(text=messages[1], font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                return

            # check if it is a boxlayout
            if not isinstance(self.layout.children[0], BoxLayout):
                self.layout.remove_widget(self.layout.children[0])

            # get pgn from response
            pgns = r.text.split('\n\n')
            games = [chess.pgn.read_game(io.StringIO(game)) for game in pgns]
            board = chess.Board()
            game = random.choice(games)

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

            # save study id to json file
            store = JsonStore('data.json')
            # check if the given study id is already in the json file
            if store.exists('study_ids'):
                ids = store.get('study_ids')['ids']
                if study_id not in ids:
                    ids.append(study_id)
                    store.put('study_ids', ids=ids)

            # change screen to waiting for board
            self.manager.transition.direction = 'left'
            self.manager.current = 'waiting_for_board'


class WaitingForBoardScreen(Screen):
    def __init__(self, **kwargs):
        super(WaitingForBoardScreen, self).__init__(**kwargs)

        # Create a GridLayout
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.back))

        self.layout.add_widget(Label(text='Waiting for board...', font_size=30, size_hint=(1, None), height=50))

        # Add the GridLayout to the screen
        self.add_widget(self.layout)

    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'opening_explorer'


class ChessApp(App):
    def build(self):
        # Set window properties
        self.title = "Certabo Chess App"
        self.icon = 'assets/icon.png'
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(OpeningExplorerScreen(name='opening_explorer'))
        sm.add_widget(WaitingForBoardScreen(name='waiting_for_board'))
        return sm


if __name__ == '__main__':
    ChessApp().run()