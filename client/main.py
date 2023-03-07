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
from kivy.core.clipboard import Clipboard
from kivy.config import Config
from kivy.utils import platform
from kivy.clock import Clock

from functools import partial
import textwrap
import chess.pgn
import time
import chess
import chess.svg
import random
import berserk
import io
import threading
import requests
from io import BytesIO
from fentoboardimage import fenToImage, loadPiecesFolder

from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent)+"\\certabo")

from utils import reader_writer, usbtool
import codes
import certabo

def launch_webbrowser(url):
    import webbrowser
    if platform == 'android':
        from jnius import autoclass, cast
        def open_url(url):
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            activity = PythonActivity.mActivity
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            browserIntent = Intent()
            browserIntent.setAction(Intent.ACTION_VIEW)
            browserIntent.setData(Uri.parse(url))
            currentActivity = cast('android.app.Activity', activity)
            currentActivity.startActivity(browserIntent)

        # Web browser support for Android
        class AndroidBrowser(object):
            def open(self, url, new=0, autoraise=True):
                open_url(url)
            def open_new(self, url):
                open_url(url)
            def open_new_tab(self, url):
                open_url(url)

        webbrowser.register('android', AndroidBrowser, None, -1)

    webbrowser.open(url)

letters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
def get_move_from_fens(fen1, fen2):
    # this function is used to get the played move from two fens
    turn = fen1.split(" ")[1] == "w"
    fen1 = fen1.split(" ")[0]
    fen2 = fen2.split(" ")[0]
    index = 0
    pieces = {}
    for i in fen1:
        if i == "/": continue
        # check if i is a number
        if i.isdigit():
            index += int(i)
            continue
        index += 1
        if turn:
            if i.isupper():
                try:
                    pieces[i.lower()].append(index)
                except:
                    pieces[i.lower()] = [index]
        else:
            if i.islower():
                try:
                    pieces[i].append(index)
                except:
                    pieces[i] = [index]
    
    index = 0
    to_square = None
    for i in fen2:
        if i == "/": continue
        # check if i is a number
        if i.isdigit():
            index += int(i)
            continue
        index += 1
        if turn:
            if i.isupper():
                try:
                    pieces[i.lower()].remove(index)
                except:
                    to_square = index
        else:
            if i.islower():
                try:
                    pieces[i].remove(index)
                except:
                    to_square = index

    # if rook and king are the only pieces left in pieces, then it is castling
    if pieces["k"] != [] and pieces["r"] != []:
        if pieces["r"] == [8]:
            # kingside castling
            return "e8g8"
        elif pieces["r"] == [1]:
            # queenside castling
            return "e8c8"
        elif pieces["r"] == [64]:
            # kingside castling
            return "e1g1"
        elif pieces["r"] == [57]:
            # queenside castling
            return "e1c1"

    # from square is the only non empty list in pieces
    from_square = [i for i in pieces.values() if len(i) == 1][0][0]
    # convert to UCI notation
    from_square = letters[(from_square - 1) % 8] + str((from_square - 1) // 8 + 1)
    to_square = letters[(to_square - 1) % 8] + str((to_square - 1) // 8 + 1)
    
    return from_square + to_square

def connect_to_certabo():
    global mycertabo, led_manager
    while mycertabo is None:
        port_chessboard = usbtool.find_address()
        if port_chessboard is None:
            # sleep for 1 second and try again
            time.sleep(1)
            continue
    
        mycertabo = certabo.Certabo(port=port_chessboard)

pieceSet = loadPiecesFolder('assets/pieces/')
server_ip = "0.0.0.0"
lichess_client = berserk.Client()
mycertabo = None

# start thread to connect to certabo board
thread = threading.Thread(target=connect_to_certabo, daemon=True)
thread.start()

# remove multitouch emulation with mouse right click.
Config.set('input', 'mouse', 'mouse,multitouch_on_demand')

messages = ["Error: Please enter a study ID", "Error: Study/Chapter does not exist, is private or no internet", "Success!", "Error: Failed to load study", "Error: Rate limit exceeded, please try again in 1 minute"]


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

        self.layout.add_widget(Button(text='Configuration', font_size=30, size_hint=(1, None), height=75, 
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
        self.before = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        self.usb_reader = None
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
        
        self.layout.add_widget(Button(text='Log into lichess', font_size=30, size_hint=(1, None), height=75,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                 padding=[20, 10], on_press=self.lichess_connection))
        
        # add text at bottom showing currently connected lichess account if any
        store = JsonStore('data.json')
        if store.exists('lichess_api_key'):
            self.layout.add_widget(Label(text='Currently logged in as: ' + store.get('lichess_api_key')["value"].split("//")[1], font_size=30, size_hint=(1, None), height=75, color=(0, 1, 0, 1)))
        else:
            self.layout.add_widget(Label(text='Currently not logged into a lichess account', font_size=30, size_hint=(1, None), height=75, color=(1, 0, 0, 1)))

        
    
    def board_connection(self, instance):
        # clear widgets
        self.layout.clear_widgets()

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.tests))

        # add text saying testing board connection
        self.layout.add_widget(Label(text='Testing to see if we have connection to board...', font_size=30, size_hint=(1, None), height=100))

        # run board connection test async
        Clock.schedule_once(self.board_connection_test, 0.1)

    def board_connection_test(self, instance):
        global mycertabo
        if mycertabo is None:
            # add text saying no board found and to connect it
            self.layout.remove_widget(self.layout.children[0])
            self.layout.add_widget(Label(text='No board found, please connect it and try again', font_size=30, size_hint=(1, None), height=100))
            # sleep for 1 second and try again
            Clock.schedule_once(self.board_connection_test, 1)
            return   
        
        # add text saying board found
        self.layout.remove_widget(self.layout.children[0])
        self.layout.add_widget(Label(text='Board found, displaying currently detected board position...', font_size=30, size_hint=(1, None), height=30))
        self.layout.add_widget(Label(text="To calibrate, please set the pieces to the starting position and extra queens to d3 and d6", font_size=20, size_hint=(1, None), height=30))
        # calibrate button
        self.layout.add_widget(Button(text='Calibrate', font_size=30, size_hint=(1, None), height=60,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                 padding=[20, 10], on_press=self.calibrate))
        # usbtool.start_usbtool(port_chessboard)
        # self.usb_reader = reader_writer.BoardReader(port_chessboard)

        led_manager.set_leds(['a1', 'a8', 'h1', 'h8'])
        print(led_manager)

        if mycertabo.board_state_usb == "":
            self.before = mycertabo.chessboard
        else:
            self.before = chess.Board(fen=mycertabo.board_state_usb)
            mycertabo.set_board_from_fen(self.before.fen())
        self.layout.add_widget(board_to_image(self.before))
        # add text displaying last played move
        Clock.schedule_once(self.update_board, 0.1)

    def calibrate(self, instance):
        mycertabo.calibration = True

    def update_board(self, instance):
        try:
            if self.manager.current != 'test' or "logged in" in self.layout.children[0].text:
                return
        except: pass
        
        # fen = self.usb_reader.read_board()
        # if fen != self.before:
        #     self.before = fen
        #     self.layout.remove_widget(self.layout.children[0])
        #     self.layout.add_widget(board_to_image(chess.Board(fen=fen)))
        # move = self.mycertabo.get_user_move()
        # self.mycertabo.chessboard.push_uci(move[0])
        self.layout.remove_widget(self.layout.children[0])
        if mycertabo.board_state_usb != "":
            self.before = chess.Board(fen=mycertabo.board_state_usb)
            mycertabo.set_board_from_fen(self.before.fen())
        else:
            self.before = mycertabo.chessboard

        self.layout.add_widget(board_to_image(self.before))
        Clock.schedule_once(self.update_board, 0.1)

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
        req = UrlRequest('http://' + ip, on_success=self.connection_success, on_failure=self.connection_failure, on_error=self.connection_failure, timeout=5)

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
        req = UrlRequest(url, on_success=self.best_move_success, on_failure=self.best_move_failure, on_error=self.best_move_failure, timeout=5)
    
    def connection_failure(self, req, result):
        global server_ip
        # add failure widget with red text
        self.layout.add_widget(Label(text='Connection to server failed!', font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
        self.layout.add_widget(Label(text='Check if the server ip is correct and that the server is running and on the same WIFI', font_size=20, size_hint=(1, None), height=40, color=(1, 0, 0, 1)))
        
        # display error
        self.layout.add_widget(Label(text=str(result), font_size=20, size_hint=(1, None), height=40, color=(1, 0, 0, 1)))

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
        self.layout.add_widget(Label(text='Failed to fetch best move!', font_size=30, size_hint=(None, None), height=40, color=(1, 0, 0, 1)))

        # display error
        self.layout.add_widget(Label(text=str(result), font_size=20, size_hint=(1, None), height=100, color=(1, 0, 0, 1)))

    def lichess_connection(self, instance):
        # clear children
        self.layout.clear_widgets()

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                padding=[20, 10], on_press=self.tests))
        
        # add text explaining
        text = 'To use the lichess integration, you need to create a lichess API key by clicking the button below. You can revoke this key at any time on the lichess website.'
        # automatically split text into new line if it is too long
        text = textwrap.fill(text, 70)
        self.layout.add_widget(Label(text=text, font_size=20, size_hint=(1, None), height=100))
        

        # add button to connect to lichess
        self.layout.add_widget(Button(text='Create Lichess API key', font_size=30, size_hint=(1, None), height=75,
                                    background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                    padding=[20, 10], on_press=self.create_key))
        
        
        # add text input to enter lichess API key
        self.layout.add_widget(Label(text='Enter your lichess API key:', font_size=30, size_hint=(1, None), height=50))
        self.text_input = TextInput(multiline=False, size_hint=(1, None), height=75,
                                    background_color=(1, 1, 1, 1),  # Set white background
                                    padding=[20, 10])
        self.layout.add_widget(self.text_input)

        # add button to connect to lichess
        self.layout.add_widget(Button(text='Connect to lichess', font_size=30, size_hint=(1, None), height=75,
                                    background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                    padding=[20, 10], on_press=self.connect_to_lichess))
        
    def create_key(self, instance):
        # check the platform
        if platform != 'ios':
            launch_webbrowser('https://lichess.org/account/oauth/token/create?scopes[]=challenge:write&scopes[]=challenge:read&scopes[]=study:read&scopes[]=board:play&description=Certabo+Board+App')
        else:
            # add error message in red
            self.layout.add_widget(Label(text='Failed to open webbrowser! IOS not supported.', font_size=20, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
            
    def connect_to_lichess(self, instance):
        global lichess_client
        lichess_api_key = self.text_input.text
        if lichess_api_key == '':
            # check if error is already displayed
            if self.layout.children[0].text != "Connect to lichess":
                self.layout.remove_widget(self.layout.children[0])

            # add error message in red
            self.layout.add_widget(Label(text='Please enter a valid lichess API key!', font_size=20, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
        else:
            # check if error is already displayed
            if self.layout.children[0].text != "Connect to lichess":
                self.layout.remove_widget(self.layout.children[0])

            # try to connect to lichess
            session = berserk.TokenSession(lichess_api_key)
            lichess_client = berserk.Client(session=session)
            username = ''

            try:
                account = lichess_client.account.get()
                # add success message in green
                self.layout.add_widget(Label(text=f"Successfully logged in as '{account['username']}'!", font_size=20, size_hint=(1, None), height=50, color=(0, 1, 0, 1)))
                # save username
                username = account['username']
            except:
                # add error message in red
                self.layout.add_widget(Label(text='Failed to connect to lichess! Please check the validity of the given API key.', font_size=20, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                return

            # save lichess API key
            store = JsonStore('data.json')
            store.put("lichess_api_key", value=f"{lichess_api_key}//{username}")
    
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
        global mycertabo
        super(GameScreen, self).__init__(**kwargs)
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}
        self.game = chess.pgn.Game(headers={"Event": "Certabo OTB Game", "Site": "Certabo Board", "Round": "1", "White": "White", "Black": "Black", "Result": "*"})
        self.node = self.game
        self.playing = False
        self.move = None

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                padding=[20, 10], on_press=self.back))
        
        self.layout.add_widget(Label(text='Set board to any position and press play', font_size=25, size_hint=(1, None), height=30))
        self.layout.add_widget(Button(text='Play', font_size=30, size_hint=(1, None), height=40,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.play))
        
        # display the board
        if mycertabo and mycertabo.board_state_usb != "":
            self.layout.add_widget(board_to_image(chess.Board(fen=mycertabo.board_state_usb)))
        else:
            self.layout.add_widget(board_to_image(chess.Board()))

        # add button to import game to lichess
        item_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)
        item_layout.add_widget(Button(text='Import to Lichess', font_size=30, size_hint=(1, None), height=50,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.import_game))
        item_layout.add_widget(Button(text='Copy PGN', font_size=30, size_hint=(1, None), height=50,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.copy_pgn))
        self.layout.add_widget(item_layout)
        
        # add text saying connecting to board
        self.layout.add_widget(Label(text='Trying to see if we have connection to board...', font_size=20, size_hint=(1, None), height=40))
        
        self.add_widget(self.layout)

        # schedule update before play
        # Clock.schedule_once(self.update_before_play, 1)

    def back(self, instance):
        self.manager.transition.direction = 'right'
        self.manager.current = 'play'

    def update_before_play(self, instance):
        global mycertabo
        if not self.playing:
            if mycertabo is not None:
                if self.layout.children[0].text == 'Trying to see if we have connection to board...' or self.layout.children[0].text == 'No board found, please connect it and try again':
                    self.layout.remove_widget(self.layout.children[0])
                    self.layout.add_widget(Label(text='Board found, press play to start', font_size=25, size_hint=(1, None), height=40))
                
                # display the board
                if mycertabo.board_state_usb != "":
                    self.layout.remove_widget(self.layout.children[2])
                    self.layout.add_widget(board_to_image(chess.Board(fen=mycertabo.board_state_usb)), 2)
                    mycertabo.set_board_from_fen(mycertabo.board_state_usb)
            
            else:
                self.layout.remove_widget(self.layout.children[0])
                self.layout.add_widget(Label(text='No board found, please connect it and try again', font_size=25, size_hint=(1, None), height=40))
            
            Clock.schedule_once(self.update_before_play, 1)
            return

    def play(self, instance):
        global mycertabo
        if mycertabo is None:
            self.layout.remove_widget(self.layout.children[0])
            self.layout.add_widget(Label(text='No board found, please connect it and try again', font_size=30, size_hint=(1, None), height=100))
            # sleep for 1 second and try again
            Clock.schedule_once(self.play, 1)
            return   
        
        # add text saying board found
        self.layout.remove_widget(self.layout.children[0])
        # remove play button
        self.layout.remove_widget(self.layout.children[2])
        # remove text saying set board to any position
        self.layout.remove_widget(self.layout.children[2])

        # sleep until mycertabo.board_state_usb is not empty
        while mycertabo.board_state_usb == '':
            time.sleep(0.1)

        if mycertabo.board_state_usb.split(" ")[0] != "pppppppp/8/8/8/8/8/PPPPPPPP/RNBQKBNR":
            mycertabo.set_board_from_fen(mycertabo.board_state_usb)
            self.game.setup(mycertabo.board_state_usb)

            self.layout.remove_widget(self.layout.children[1])
            self.layout.add_widget(widget=board_to_image(mycertabo.chessboard), index=1)
        
        self.playing = True

        # add button for new game
        self.layout.add_widget(Button(text='New Game', font_size=30, size_hint=(1, None), height=40,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background
                                padding=[20, 10], on_press=self.new_game))
        

        # start new thread to get move
        thread = threading.Thread(target=self.get_move, daemon=True)
        thread.start()
        Clock.schedule_once(self.update_board, 0.1)

    def new_game(self, instance):
        global mycertabo
        mycertabo.new_game()
        self.layout.remove_widget(self.layout.children[2])
        self.layout.add_widget(widget=board_to_image(mycertabo.chessboard), index=2)
        self.game = chess.pgn.Game(headers={"Event": "Certabo OTB Game", "Site": "Certabo Board", "Round": "1", "White": "White", "Black": "Black", "Result": "*"})
        self.node = self.game
        self.move = None
        
    def update_board(self, instance):
        if self.manager.current != 'game':
            return
        
        if self.move is None:
            Clock.schedule_once(self.update_board, 0.1)
            return
        
        mycertabo.chessboard.push_uci(self.move[0])
        self.layout.remove_widget(self.layout.children[2])
        self.layout.add_widget(widget=board_to_image(mycertabo.chessboard), index=2)
        self.node = self.node.add_variation(chess.Move.from_uci(self.move[0]))
        self.move = None

        # start new thread to get move
        thread = threading.Thread(target=self.get_move, daemon=True)
        thread.start()

        Clock.schedule_once(self.update_board, 0.1)

    # non blocking thread function to get move
    def get_move(self):
        self.move = mycertabo.get_user_move()
    
    def import_game(self, instance):
        pgn = self.game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=False))

        # send post request to lichess.org/api/import
        try:
            store = JsonStore('data.json')
            if store.exists('lichess_api_key'):
                key = store.get('lichess_api_key')['value'].split("//")[0]
                r = berserk.TokenSession(key).post("https://lichess.org/api/import", data={"pgn": pgn})
            else:
                r = requests.post("https://lichess.org/api/import", data={"pgn": pgn})

            # if status is 429, it means we are being rate limited, so give error to wait 1 minute
            if r.status_code == 429:
                self.layout.add_widget(Label(text=messages[4], font_size=20, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                Clock.schedule_once(self.remove_copy_text, 3)
                return
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            # check if it is a boxlayout
            if not isinstance(self.layout.children[0], Button):
                self.layout.remove_widget(self.layout.children[0])

            # add error label with red text
            self.layout.add_widget(Label(text="Unable to import to lichess", font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
            Clock.schedule_once(self.remove_copy_text, 3)
            return
        
        url = r.json()["url"]
        Clipboard.copy(url)
        # add text displaying that game was imported with link to game
        self.layout.add_widget(Label(text='Lichess import URL copied to clipboard', font_size=30, size_hint=(1, None), height=50, color=(0, 1, 0, 1)))
        Clock.schedule_once(self.remove_copy_text, 3)

    def copy_pgn(self, instance):
        pgn = self.game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=False))
        Clipboard.copy(pgn)
        # add text displaying that pgn was copied for 3 seconds
        self.layout.add_widget(Label(text='PGN copied to clipboard', font_size=30, size_hint=(1, None), height=100, color=(0, 1, 0, 1)))
        Clock.schedule_once(self.remove_copy_text, 3)
    
    def remove_copy_text(self, instance):
        self.layout.remove_widget(self.layout.children[0])


class OpeningExplorerScreen(Screen):
    def __init__(self, **kwargs):
        super(OpeningExplorerScreen, self).__init__(**kwargs)
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.game = chess.pgn.Game()
        self.games = []
        self.node = self.game
        self.move = None
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}
        # self.mycertabo = certabo.Certabo(calibrate=False)

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
        global mycertabo
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
                store = JsonStore('data.json')
                if store.exists('lichess_api_key'):
                    key = store.get('lichess_api_key')['value'].split("//")[0]
                    r = berserk.TokenSession(key).get(url)
                else:
                    r = requests.get(url)

                # if status is 429, it means we are being rate limited, so give error to wait 1 minute
                if r.status_code == 429:
                    self.layout.add_widget(Label(text=messages[4], font_size=20, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                    return
                r.raise_for_status()
            except:
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
            pgns = r.text.split('\n\n\n')
            self.games = [chess.pgn.read_game(io.StringIO(game)) for game in pgns]
            self.game = random.choice(self.games)
            try:
                self.node = self.game.variations[0]
            except:
                # display error
                self.layout.add_widget(Label(text="Error occured when trying to load PGN", font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
                return
            
            self.orientation = self.game.headers['Orientation']

            mycertabo.set_board_from_fen(self.game.board().fen())

            # clear widgets
            self.layout.clear_widgets()
            # add back button
            self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                padding=[20, 10], on_press=self.back))
            # add board
            self.layout.add_widget(board_to_image(mycertabo.chessboard, flipped=(self.orientation == 'black')))

            # add buttons
            item_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

            item_layout.add_widget(Button(text='New', size_hint=(1, None), height=50, on_release=self.new))
            item_layout.add_widget(Button(text='Correct Move', size_hint=(1, None), height=50, on_release=self.play_correct))

            self.layout.add_widget(item_layout)

            # add text saying to make a move
            self.layout.add_widget(Label(text="Make the next move", font_size=30, size_hint=(1, None), height=50))

            if self.orientation == 'white' and mycertabo.chessboard.turn == chess.BLACK:
                mycertabo.chessboard.push(self.node.move)
            elif self.orientation == 'black' and mycertabo.chessboard.turn == chess.WHITE:
                mycertabo.chessboard.push(self.node.move)

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

            # start new thread to get move
            thread = threading.Thread(target=self.get_move, daemon=True)
            thread.start()

            Clock.schedule_once(self.update_board, 0.1)

    def play_correct(self, instance):
        mycertabo.chessboard.push(self.node.move)
        self.layout.remove_widget(self.layout.children[0])
        self.layout.add_widget(Label(text="Make the next move", font_size=30, size_hint=(1, None), height=50))
        self.move = None

        if not self.node.variations:
            self.layout.remove_widget(self.layout.children[0])
            # add text saying end of study
            self.layout.add_widget(Label(text="End of Study", font_size=30, size_hint=(1, None), height=50))
            # update board
            self.layout.remove_widget(self.layout.children[2])
            self.layout.add_widget(widget=board_to_image(mycertabo.chessboard, flipped=(self.orientation == 'black')), index=2)
            # flash leds by setting board to empty and then back to current board after 1 second
            board = mycertabo.chessboard
            mycertabo.set_board_from_fen("8/8/8/8/8/8/8/8 w - - 0 1")
            time.sleep(1)
            mycertabo.set_board_from_fen(board.fen())
            self.move = None
            Clock.schedule_once(self.update_board, 0.1)
            return

        if len(self.node.variations) > 1:
            # get all possible moves for all variations
            moves = []
            for idx, variation in enumerate(self.node.variations):
                moves.append((idx, variation.move))
            # pick a random move
            move = random.choice(moves)
            self.node = self.node.variations[move[0]]
            mycertabo.chessboard.push(self.node.move)
        else:
            self.node = self.node.variations[0]
            mycertabo.chessboard.push(self.node.move)

        self.layout.remove_widget(self.layout.children[2])
        self.layout.add_widget(widget=board_to_image(mycertabo.chessboard, flipped=(self.orientation == 'black')), index=2)
        try:
            self.node = self.node.variations[0]
        except IndexError:
            # add text saying end of study
            self.layout.remove_widget(self.layout.children[0])
            self.layout.add_widget(Label(text="End of Study", font_size=30, size_hint=(1, None), height=50))
            return

    def new(self, instance):
        self.game = random.choice(self.games)
        self.node = self.game.variations[0]
        self.move = None
        self.orientation = self.game.headers['Orientation']
        
        mycertabo.set_board_from_fen(self.game.board().fen())

         # clear widgets
        self.layout.clear_widgets()
        # add back button
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                padding=[20, 10], on_press=self.back))
        # add board
        self.layout.add_widget(board_to_image(mycertabo.chessboard, flipped=(self.orientation == 'black')))

        # add buttons
        item_layout = BoxLayout(orientation='horizontal', size_hint_y=None, height=50)

        item_layout.add_widget(Button(text='New', size_hint=(1, None), height=50, on_release=self.new))
        item_layout.add_widget(Button(text='Correct Move', size_hint=(1, None), height=50, on_release=self.play_correct))

        self.layout.add_widget(item_layout)
        
        # add text saying to make a move
        self.layout.add_widget(Label(text="Make the next move", font_size=30, size_hint=(1, None), height=50))

        if self.orientation == 'white' and mycertabo.chessboard.turn == chess.BLACK:
            mycertabo.chessboard.push(self.node.move)
        elif self.orientation == 'black' and mycertabo.chessboard.turn == chess.WHITE:
            mycertabo.chessboard.push(self.node.move)


    def update_board(self, instance):
        if self.manager.current != 'opening_explorer':
            return
                
        if self.move is None:
            Clock.schedule_once(self.update_board, 0.1)
            return
        
        if self.move != self.node.move.uci():
            self.layout.remove_widget(self.layout.children[0])
            # add text saying wrong move
            self.layout.add_widget(Label(text="Wrong Move", font_size=30, size_hint=(1, None), height=50, color=(1, 0, 0, 1)))
            self.move = None
        else:
            mycertabo.chessboard.push(self.node.move)
            self.layout.remove_widget(self.layout.children[0])
            self.layout.add_widget(Label(text="Correct! Make the next move", font_size=30, size_hint=(1, None), height=50, color=(0, 1, 0, 1)))
            self.move = None

            if not self.node.variations:
                self.layout.remove_widget(self.layout.children[0])
                # add text saying end of study
                self.layout.add_widget(Label(text="End of Study", font_size=30, size_hint=(1, None), height=50))
                # update board
                self.layout.remove_widget(self.layout.children[2])
                self.layout.add_widget(widget=board_to_image(mycertabo.chessboard, flipped=(self.orientation == 'black')), index=2)
                # flash leds by setting board to empty and then back to current board after 1 second
                board = mycertabo.chessboard
                mycertabo.set_board_from_fen("8/8/8/8/8/8/8/8 w - - 0 1")
                time.sleep(1)
                mycertabo.set_board_from_fen(board.fen())
                time.sleep(1)
                mycertabo.set_board_from_fen("8/8/8/8/8/8/8/8 w - - 0 1")
                time.sleep(1)
                mycertabo.set_board_from_fen(board.fen())
                self.move = None
                Clock.schedule_once(self.update_board, 0.1)
                return

            if len(self.node.variations) > 1:
                # get all possible moves for all variations
                moves = []
                for idx, variation in enumerate(self.node.variations):
                    moves.append((idx, variation.move))
                # pick a random move
                move = random.choice(moves)
                self.node = self.node.variations[move[0]]
                mycertabo.chessboard.push(self.node.move)
            else:
                self.node = self.node.variations[0]
                mycertabo.chessboard.push(self.node.move)

            self.layout.remove_widget(self.layout.children[2])
            self.layout.add_widget(widget=board_to_image(mycertabo.chessboard, flipped=(self.orientation == 'black')), index=2)
            try:
                self.node = self.node.variations[0]
            except IndexError:
                # add text saying end of study
                self.layout.remove_widget(self.layout.children[0])
                self.layout.add_widget(Label(text="End of Study", font_size=30, size_hint=(1, None), height=50))
                return

        thread = threading.Thread(target=self.get_move, daemon=True)
        thread.start()
        Clock.schedule_once(self.update_board, 0.1)

    def get_move(self):
        self.move = mycertabo.get_user_move()[0]

class WaitingForBoardScreen(Screen):
    def __init__(self, **kwargs):
        super(WaitingForBoardScreen, self).__init__(**kwargs)

        # Create a GridLayout
        self.layout = GridLayout(padding=20, spacing=10)
        self.layout.cols = 1
        self.layout.size_hint = (0.8, 0.4)
        self.layout.pos_hint = {'center_x': 0.5, 'center_y': 0.8}
        self.game = chess.pgn.Game()
        self.node = self.game

        # add back button to top left corner, it should be small
        self.layout.add_widget(Button(text='Back', font_size=30, size_hint=(None, None), height=50, width=100,
                                 background_color=(0.5, 0.5, 0.5, 1),  # Set gray background    
                                    padding=[20, 10], on_press=self.back))

        self.layout.add_widget(Label(text='Waiting for board...', font_size=30, size_hint=(1, None), height=50))

        # Add the GridLayout to the screen
        self.add_widget(self.layout)
    
    def get_move(self, instance):
        pass
        # if self.layout.children[0].text == 'Start':
        #     self.layout.remove_widget(self.layout.children[0])
        # move = self.mycertabo.get_user_move()[0]
        # self.mycertabo.chessboard.push_uci(move)
        # self.node = self.node.add_variation(self.mycertabo.chessboard.peek())
        # self.layout.remove_widget(self.layout.children[0])
        # self.layout.add_widget(board_to_image(self.mycertabo.chessboard))
        # pgn = self.game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=False))
        # print(pgn)
        # Clock.schedule_once(self.get_move, 0.5)

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