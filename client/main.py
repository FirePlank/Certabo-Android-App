from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.storage.jsonstore import JsonStore
from kivy.network.urlrequest import UrlRequest
from kivy.config import Config

from functools import partial
import chess.pgn
import chess
import chess.svg
import random
import berserk
from io import BytesIO
from fentoboardimage import fenToImage, loadPiecesFolder

pieceSet = loadPiecesFolder('assets/pieces/')
server_ip = "0.0.0.0"

# remove multitouch emulation with mouse right click.
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

messages = ["Error: Please enter a study ID", "Error: Study/Chapter does not exist or is private", "Success!", "Error: Failed to load study", "Error: Rate limit exceeded, please try again in 1 minute"]


def board_to_image(board: chess.Board, flipped: bool = False, height: int = 300):
    try:
        last_move = str(board.peek())
        last_move_dict = {"before": last_move[:2], "after": last_move[2:], "darkColor": "#aaa23a", "lightColor": "#cdd26a"}
    except IndexError:
        # no moves have been made yet
        last_move_dict = None

    boardImage = fenToImage(
        fen=board.fen(),
        squarelength=100,
        pieceSet=pieceSet,
        darkColor="#D18B47",
        lightColor="#FFCE9E",
        flipped=flipped,
        lastMove=last_move_dict
    )

    # fancy code to be able to display a PIL image without having to save it to a file first
    data = BytesIO()
    boardImage.save(data, format='png')
    data.seek(0)
    im = CoreImage(BytesIO(data.read()), ext='png')
    return Image(texture=im.texture, size_hint=(1, None), height=height)


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
        self.layout.add_widget(Button(text='Play Offline', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10], on_press=self.play_screen))

        self.layout.add_widget(Button(text='Opening Explorer', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10], on_press=self.opening_explorer))

        self.layout.add_widget(Button(text='Tests and Configuration', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10], on_press=self.test_screen))
        
        self.add_widget(self.layout)

    def play_screen(self, instance):
        self.manager.transition.direction = 'left'
        self.manager.current = 'play'

    def opening_explorer(self, instance):
        self.manager.transition.direction = 'left'
        self.manager.current = 'opening_explorer'

    def test_screen(self, instance):
        self.manager.transition.direction = 'left'
        self.manager.current = 'test'


class TestScreen(Screen):
    def __init__(self, **kwargs):
        super(TestScreen, self).__init__(**kwargs)
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.board = chess.Board()
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}

        self.tests()

        self.add_widget(self.layout)

    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'main'

    def tests(self, instance=None):
        self.layout.clear_widgets()
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.back))

        self.layout.add_widget(Button(text='Test Connection to Board / Calibration', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10], on_press=self.board_connection))

        self.layout.add_widget(Button(text='Test Connection to Server', font_size=30, size_hint=(1, None), height=75, 
                               background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                               padding=[20, 10], on_press=self.engine_test))
    
    def board_connection(self, instance):
        # clear widgets
        self.layout.clear_widgets()

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.tests))

        # add text saying testing board connection
        self.layout.add_widget(Label(text='Testing to see if we have connection to board...', font_size=30, size_hint=(1, None), height=100))

    def engine_test(self, instance):
        global server_ip
        if server_ip != "0.0.0.0":
            # skip straight to server connection test
            self.ip_input.text = server_ip
            self.submit_ip(None)
            return
        
        # clear widgets
        self.layout.clear_widgets()

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.tests))

        # add text input to enter server ip
        self.layout.add_widget(Label(text='Enter server IP:', font_size=30, size_hint=(1, None), height=100))
        self.ip_input = TextInput(text='', multiline=False, font_size=30, size_hint=(1, None), height=100)
        self.layout.add_widget(self.ip_input)

        # submit button
        self.layout.add_widget(Button(text='Submit', font_size=30, size_hint=(1, None), height=75,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.submit_ip))
        
    def submit_ip(self, instance):
        # clear widgets
        self.layout.clear_widgets()

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.tests))

        # add text saying testing board connection
        self.layout.add_widget(Label(text='Testing to see if we have connection to server...', font_size=30, size_hint=(1, None), height=40))

        # parse http and port from ip
        ip = self.ip_input.text
        ip = ip.replace('http://', '')
        ip = ip.replace('https://', '')
        if ':' not in ip:
            ip += ':5000'

        # asyncronously test connection to server
        req = UrlRequest('http://' + ip, on_success=self.connection_success, on_failure=self.connection_failure, timeout=5)

    def connection_success(self, req, result):
        global server_ip
        # add success widget
        self.layout.add_widget(Label(text='Connection to server successful!', font_size=30, size_hint=(1, None), height=40))
        server_ip = self.ip_input.text
        server_ip = server_ip.replace('http://', '')
        server_ip = server_ip.replace('https://', '')
        # remove trailing slash
        if server_ip[-1] == '/':
            server_ip = server_ip[:-1]
        if ':' not in server_ip:
            server_ip += ':5000'

        # play a game computer vs computer
        self.layout.add_widget(Label(text='Making the computer play a game against itself...', font_size=30, size_hint=(1, None), height=40))

        self.layout.add_widget(board_to_image(self.board))
        url = 'http://' + server_ip + '/move?fen=' + self.board.fen()
        # convert url to url encoded string
        url = url.replace(' ', '%20')
        req = UrlRequest(url, on_success=self.best_move_success, on_failure=self.best_move_failure, timeout=5)
    
    def connection_failure(self, req, result):
        global server_ip
        # add failure widget with red text
        self.layout.add_widget(Label(text='Connection to server failed!', font_size=30, size_hint=(1, None), height=100, color=(1, 0, 0, 1)))
        self.layout.add_widget(Label(text='Check if the server ip is correct and that the server is running and on the same WIFI', font_size=20, size_hint=(1, None), height=100, color=(1, 0, 0, 1)))
        
        # display error
        self.layout.add_widget(Label(text=str(result), font_size=20, size_hint=(1, None), height=100, color=(1, 0, 0, 1)))

        # remove server_ip
        server_ip = "0.0.0.0"

    def best_move_success(self, req, result):
        # make the best move
        try:
            self.board.push_uci(str(result))
        except:
            self.best_move_failure(req, "Invalid move received: " + str(result))

        # remove the image of the board, or the last added image
        self.layout.remove_widget(self.layout.children[0])
        # create a new image
        self.layout.add_widget(board_to_image(self.board))

        # if game is over, then display the result
        if self.board.is_game_over(claim_draw=True):
            self.layout.add_widget(Label(text='Game over!', font_size=30, size_hint=(1, None), height=40))
            self.board.reset()
            return
        else:
            # self.layout.add_widget(board_to_image(self.board))
            url = 'http://' + server_ip + '/move?fen=' + self.board.fen()
            # convert url to url encoded string
            url = url.replace(' ', '%20')
            # play the next move
            req = UrlRequest(url, on_success=self.best_move_success, on_failure=self.best_move_failure, timeout=5)

    def best_move_failure(self, req, result):
        # add failure widget with red text
        self.layout.add_widget(Label(text='Failed to fetch best move!', font_size=30, size_hint=(None, None), height=100, color=(1, 0, 0, 1)))

        # display error
        self.layout.add_widget(Label(text=str(result), font_size=20, size_hint=(1, None), height=100, color=(1, 0, 0, 1)))


class PlayScreen(Screen):
    def __init__(self, **kwargs):
        super(PlayScreen, self).__init__(**kwargs)

        # Create a GridLayout
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}

        self.selection(None)

        # Add the GridLayout to the screen
        self.add_widget(self.layout)

    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'main'
    
    def selection(self, instance):
        #  clear children and ask if they want to play computer or human
        self.layout.clear_widgets()
        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                padding=[20, 10], on_press=self.back))

        # ask if they want to play computer or human
        self.layout.add_widget(Label(text='Play against:', font_size=30, size_hint=(1, None), height=100))

        # add buttons for different options
        self.layout.add_widget(Button(text='Computer', font_size=30, size_hint=(1, None), height=75,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.computer))
        self.layout.add_widget(Button(text='Human', font_size=30, size_hint=(1, None), height=75,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.human))

    def computer(self, instance):
        # clear children and ask if they want to play white or black
        self.layout.clear_widgets()
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.selection))
        self.layout.add_widget(Label(text='Play as:', font_size=30, size_hint=(1, None), height=100))
        self.layout.add_widget(Button(text='White', font_size=30, size_hint=(1, None), height=75,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.white))
        self.layout.add_widget(Button(text='Black', font_size=30, size_hint=(1, None), height=75,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.black))
        
    def white(self, instance):
        self.manager.side = 'white'
        self.manager.transition.direction = 'left'
        self.manager.current = 'game'
    
    def black(self, instance):
        self.manager.side = 'black'
        self.manager.transition.direction = 'left'
        self.manager.current = 'game'
            
    def human(self, instance):
        self.manager.side = 'human'
        self.manager.transition.direction = 'left'
        self.manager.current = 'game'


class GameScreen(Screen):
    def __init__(self, **kwargs):
        super(GameScreen, self).__init__(**kwargs)
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                padding=[20, 10], on_press=self.back))

        self.add_widget(self.layout)

    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'play'


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

        # Create the dropdown menu for selecting previous ids
        store = JsonStore('data.json')
        self.dropdown = DropDown()
        
        if store.exists('study_ids'):
             # Create the button widget
            self.button = Button(text='Select previously used IDs', size_hint=(1, None), height=75,
                            background_color=(1, 1, 1, 1),  # Set white background
                            padding=[20, 10],
                            font_size=20)
            # Set the button to open the dropdown when clicked
            self.button.bind(on_release=self.dropdown.open)
             # Add the button to the layout
            self.layout.add_widget(self.button)

            for id in store.get('study_ids')['ids']:
                # Create a BoxLayout to hold the label and the trash icon
                item_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=44)

                # Add the label to the layout
                btn = Button(text=id, size_hint=(0.8, 1))
                btn.bind(on_release=lambda btn: self.dropdown.select(btn.text))

                # Add the trash icon to the layout
                trash_icon = Button(background_normal='assets/trash.png', size_hint=(None, None), size=(45,40))    
                trash_icon.bind(on_release=partial(self.remove_id, id))

                # Add the label and the trash icon to the layout
                item_layout.add_widget(btn)
                item_layout.add_widget(trash_icon)

                # Add the layout to the dropdown
                self.dropdown.add_widget(item_layout)

        self.dropdown.bind(on_select=lambda instance, x: setattr(self.text_input, 'text', x))

        # Set the maximum height of the dropdown
        self.dropdown.max_height = 200

        # Set the scrollbar to only show when necessary
        # self.dropdown.scroll_view.bar_width = 5

        # Set the background color of the dropdown
        self.dropdown.background_color = (1, 1, 1, 1)

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

    
    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'main'

    def remove_id(self, id, instance):
        store = JsonStore('data.json')
        if store.exists('study_ids'):
            ids = store.get('study_ids')['ids']
            if id in ids:
                ids.remove(id)
                store.put('study_ids', ids=ids)
                self.refresh_dropdown()

    def refresh_dropdown(self):
        self.dropdown.clear_widgets()
        store = JsonStore('data.json')
        if store.exists('study_ids'):
            for id in store.get('study_ids')['ids']:
                # Create a BoxLayout to hold the label and the trash icon
                item_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=44)

                # Add the label to the layout
                btn = Button(text=id, size_hint=(0.8, 1))
                btn.bind(on_release=lambda btn: self.dropdown.select(btn.text))

                # Add the trash icon to the layout
                trash_icon = Button(background_normal='assets/trash.png', size_hint=(None, None), size=(45,40))    
                trash_icon.bind(on_release=partial(self.remove_id, id))

                # Add the label and the trash icon to the layout
                item_layout.add_widget(btn)
                item_layout.add_widget(trash_icon)

                # Add the layout to the dropdown
                self.dropdown.add_widget(item_layout)
    

    def callback(self, instance, tries=0):
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
            variations = "?orientation=true?variations=false" if not self.checkbox.active else "?orientation=true"

            # if study id contains a slash, it means they want a specific chapter
            if '/' in study_id:
                url = f'https://lichess.org/study/{study_id}.pgn{variations}'
            else:
                url = f'https://lichess.org/api/study/{study_id}.pgn{variations}'

            # check if study exists
            try:
                r = requests.get(url)
                # if status is 429, it means we are being rate limited, so give error to wait 1 minute
                if r.status_code == 429:
                    self.layout.add_widget(Label(text=messages[4], font_size=20, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                    return
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

            # print(game.headers['Orientation'])

            try: node = game.next()
            except Exception as e:
                print(e)
                # retry function
                if tries == 3:
                    self.layout.add_widget(Label(text=messages[3], font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                    return
                self.callback(instance, tries+1)

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
            else:
                store.put('study_ids', ids=[study_id])

            # clear text input
            self.text_input.text = ''
            # refresh dropdown
            self.refresh_dropdown()

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
        sm.add_widget(PlayScreen(name='play'))
        sm.add_widget(OpeningExplorerScreen(name='opening_explorer'))
        sm.add_widget(WaitingForBoardScreen(name='waiting_for_board'))
        sm.add_widget(TestScreen(name='test'))
        sm.add_widget(GameScreen(name='game'))
        return sm


if __name__ == '__main__':
    ChessApp().run()