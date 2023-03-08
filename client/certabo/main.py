# TODO: Fix error when exiting during splash screen!
import json
import logging
import multiprocessing
import os
import queue
import sys
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import chess
import chess.pgn
import chess.engine
import pygame
import pygame.gfxdraw

import cfg
import pypolyglot  # TODO: Use Python-chess
import stockfish   # TODO: Remove after using Python-chess for hint
from messchess import RomEngine  # TODO: Try to use Python-chess
from publish import Publisher

from utils.analysis_engine import GameEngine, AnalysisEngine
from utils.get_moves import get_moves, is_move_back
from utils.game_clock import GameClock
from utils.remote_control import RemoteControl
from utils import media, logger, reader_writer, usbtool
from utils.media import create_button, coords_in, show_text, show_sprite, play_audio, COLORS
from utils.get_books_engines import get_book_list, get_engine_list, CERTABO_SAVE_PATH

from utils.reader_writer import FEN_SPRITE_MAPPING, COLUMNS_LETTERS
from utils.logger import CERTABO_DATA_PATH

if __name__ == '__main__':
    multiprocessing.freeze_support()

    logger.set_logger()

    # Use stockfish.exe if running built. Not sure if needed
    TO_EXE = getattr(sys, "frozen", False)
    stockfish.TO_EXE = TO_EXE

    # TODO: Move this to publish.py
    def make_publisher():
        global pgn_queue, publisher
        if publisher:
            publisher.stop()
        pgn_queue = queue.Queue()
        publisher = Publisher(cfg.args.publish, pgn_queue, cfg.args.game_id, cfg.args.game_key)
        publisher.start()
        return pgn_queue, publisher


    def publish():
        global pgn_queue
        pgn_queue.put(generate_pgn())


    def check_input_events():
        left_click = False
        for event in pygame.event.get():  # all values in event list
            if event.type == pygame.QUIT:
                do_poweroff(method='window')
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    do_poweroff(method='key')
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                left_click = True

        x, y = pygame.mouse.get_pos()
        x = x / cfg.x_multiplier
        y = y / cfg.y_multiplier
        return x, y, left_click


    def do_poweroff(method=None):
        if method == 'logo':
            logging.info('Closing program: logo click')
        elif method == 'key':
            logging.info('Closing program: q key')
        elif method == 'window':
            logging.info('Closing program: window closed')
        elif method == 'remote_control':
            logging.info('Closing program: remote control')
        else:
            logging.warning('Closing program: unknown method')

        if publisher is not None:
            publisher.stop()

        for thread in (analysis_engine, game_engine):
            if thread is not None:
                thread.kill()

        try:
            led_manager.set_leds()
            time.sleep(.750)  # Allow sometime to send led instruction before killing usbtool!
        except NameError:
            pass

        try:
            chessboard_connection_process.kill()
            chessboard_connection_process.join()
            time.sleep(.250)  # Give enough time to make sure usbtool is killed!
        except NameError:
            pass
        except AttributeError:
            pass

        pygame.display.quit()
        pygame.quit()
        sys.exit()


    def show_board(FEN_string, x0=178, y0=40, rotate=True):
        # Show chessboard using FEN string like
        # "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        show_sprite("chessboard_xy", x0, y0)

        FEN_string = FEN_string.split(' ')[0]
        if rotate and game_settings['rotate180']:
            FEN_string = FEN_string[::-1]

        x, y = 0, 0
        for c in FEN_string:
            if c in FEN_SPRITE_MAPPING:
                show_sprite(FEN_SPRITE_MAPPING[c], x0 + 26 + 31.8 * x, y0 + 23 + y * 31.8)
                x += 1
            elif c == "/":  # new line
                x = 0
                y += 1
            elif c == 'X':  # Missing piece
                x += 1
            else:
                x += int(c)


    def show_board_and_animated_move(FEN_string, move, x0, y0, frames=30):
        piece = ""
        if game_settings['rotate180']:
            FEN_string = "/".join(
                row[::-1] for row in reversed(FEN_string.split(" ")[0].split("/"))
            )

        xa = COLUMNS_LETTERS.index(move[0])
        ya = 8 - int(move[1])
        xb = COLUMNS_LETTERS.index(move[2])
        yb = 8 - int(move[3])

        if game_settings['rotate180']:
            xa = 7 - xa
            ya = 7 - ya
            xb = 7 - xb
            yb = 7 - yb

        xstart, ystart = x0 + 26 + 31.8 * xa, y0 + 23 + ya * 31.8
        xend, yend = x0 + 26 + 31.8 * xb, y0 + 23 + yb * 31.8

        show_sprite("chessboard_xy", x0, y0)
        x, y = 0, 0
        for c in FEN_string:

            if c in FEN_SPRITE_MAPPING:
                if x != xa or y != ya:
                    show_sprite(FEN_SPRITE_MAPPING[c], x0 + 26 + 31.8 * x, y0 + 23 + y * 31.8)
                else:
                    piece = FEN_SPRITE_MAPPING[c]
                x += 1
            elif c == "/":  # new line
                x = 0
                y += 1
            elif c == " ":
                break
            else:
                x += int(c)
                # pygame.display.flip() # copy to screen
        if piece == "":
            return
        # logging.debug(f'Animating {piece}')
        for i in range(frames):
            x, y = 0, 0
            show_sprite("chessboard_xy", x0, y0)
            for c in FEN_string:
                if c in FEN_SPRITE_MAPPING:
                    if x != xa or y != ya:
                        show_sprite(FEN_SPRITE_MAPPING[c], x0 + 26 + 31.8 * x, y0 + 23 + y * 31.8)
                    x += 1
                elif c == "/":  # new line
                    x = 0
                    y += 1
                elif c == " ":
                    break
                else:
                    x += int(c)

            xp = xstart + (xend - xstart) * i / frames
            yp = ystart + (yend - ystart) * i / frames
            show_sprite(piece, xp, yp)
            pygame.display.flip()  # copy to screen


    def terminal_print(s, newline=True):
        """
        Print lines in virtual terminal. Does not repeat previous line
        """
        global terminal_lines
        if newline:
            # If line is different than previous
            if s != terminal_lines[1]:
                terminal_lines = [terminal_lines[1], s]
        else:
            terminal_lines[1] = "{}{}".format(terminal_lines[1], s)


    def generate_pgn():
        move_history = [_move.uci() for _move in chessboard.move_stack]
        game = chess.pgn.Game()
        game.headers["Date"] = datetime.now().strftime("%Y.%m.%d")
        if game_settings['play_white']:
            game.headers["White"] = "Human"
            game.headers["Black"] = "Computer" if not game_settings['human_game'] else "Human"
        else:
            game.headers["White"] = "Computer" if not game_settings['human_game'] else "Human"
            game.headers["Black"] = "Human"
        game.headers["Result"] = chessboard.result()
        game.setup(chess.Board(starting_position, chess960=game_settings['chess960']))
        if len(move_history) > 2:
            node = game.add_variation(chess.Move.from_uci(move_history[0]))
            for move in move_history[1:]:
                node = node.add_variation(chess.Move.from_uci(move))
        exporter = chess.pgn.StringExporter()
        return game.accept(exporter)

    # TODO: Highlight leds that need to be fixed
    def take_back_steps():
        """
        Helper function to set settings after take back was confirmed
        """
        global game_settings
        global waiting_for_user_move
        global do_user_move
        global banner_fix_pieces
        global banner_certabo_move
        global hint_text
        global show_analysis
        global led_manager
        global board_state

        logging.debug(f'Take back: Before - {chessboard.fen()}')
        logging.info(f'Take back: Before - {str([_move.uci() for _move in chessboard.move_stack])}')
        chessboard.pop()
        if not game_settings['human_game']:
            chessboard.pop()
        logging.info(f'Take back: After - {str([_move.uci() for _move in chessboard.move_stack])}')
        logging.debug(f'Take back: After - {chessboard.fen()}')
        waiting_for_user_move = False
        do_user_move = False
        banner_certabo_move = False
        banner_fix_pieces = True
        hint_text = ""
        show_analysis = False
        led_manager.set_leds()


    # ----------- Create Pygame Window
    xresolution = 'auto'
    fullscreen = False
    with open("screen.ini", "r") as f:
        try:
            xresolution = f.readline().split(" #")[0].strip()
            if xresolution != 'auto':
                xresolution = int(xresolution)
        except Exception as e:
            logging.warning(f"Cannot read resolution from first line of screen.ini: {e}")

        try:
            s = f.readline().split(" #")[0].strip()
            if s == 'fullscreen':
                fullscreen = True
        except Exception as e:
            logging.warning(f"Cannot read 'fullscreen' or 'window' from second line of screen.ini: {e}")


    os.environ["SDL_VIDEO_CENTERED"] = "1"
    # os.environ['SDL_AUDIODRIVER'] = 'dsp'
    try:
        pygame.mixer.init()
    except pygame.error as e:
        logging.error(f'Failed to load audio driver {e}')
    pygame.init()

    # auto reduce a screen's resolution
    infoObject = pygame.display.Info()
    xmax, ymax = infoObject.current_w, infoObject.current_h
    logging.info(f"Screen size = {xmax}px x {ymax}px")

    sprite_resolutions = (1920, 1366, 1024, 800, 480)
    window_sizes = ((1500, 1000),
                    (900, 600),
                    (800, 533),
                    (625, 417),
                    (480, 320))

    # Check if screen.ini resolution is not too large for user screen
    if xresolution != 'auto':
        try:
            index = sprite_resolutions.index(xresolution)
        except ValueError:
            logging.warning(f"Resolution defined on screen.ini = {xresolution} is not supported. Defaulting to 'auto'")
            xresolution = 'auto'
        else:
            x, y = window_sizes[index]
            if xmax >= x and ymax >= y:
                screen_width = x
                screen_height = y
            else:
                logging.warning(f"Resolution defined on screen.ini = {xresolution} is too large for the detected screen size. Defaulting to 'auto'.")
                xresolution = 'auto'

    # Find largest resolution automatically
    if xresolution == 'auto':
        if not fullscreen:
            ymax -= 100  # Leave 100px margin for os taskbar when not running in fullscreen

        for xres, (x, y) in zip(sprite_resolutions, window_sizes):
            if xmax >= x and ymax >= y:
                xresolution = xres
                screen_width = x
                screen_height = y
                break
        else:  # Nobreak
            raise SystemError('Screen resolution is too small! Screen must be at least 480px x 320px.')

    logging.info(f'Running game with xresolution = {xresolution}')
    logging.info(f'Running game with window size = {screen_width}px x {screen_height}px')

    cfg.xresolution = xresolution
    cfg.x_multiplier = screen_width / 480
    cfg.y_multiplier = screen_height / 320

    screen_options = pygame.HWSURFACE | pygame.DOUBLEBUF
    if fullscreen:
        screen_options |= pygame.FULLSCREEN
    cfg.scr = pygame.display.set_mode((screen_width, screen_height), screen_options, 32)
    pygame.display.set_caption("Chess software")
    pygame.display.flip()  # copy to screen

    media.load_sprites(xresolution)
    media.load_audio()
    media.load_fonts()

    # change mouse cursor to be invisible - not needed for Windows!
    if cfg.args.hide_cursor:
        mc_strings = '        ', '        ', '        ', '        ', '        ', '        ', '        ', '        '
        cursor, mask = pygame.cursors.compile(mc_strings)
        cursor_sizer = ((8, 8), (0, 0), cursor, mask)
        pygame.mouse.set_cursor(*cursor_sizer)

    # ------------- Define initial variables
    if cfg.args.syzygy is None:
        cfg.args.syzygy = os.path.join(CERTABO_DATA_PATH, 'syzygy')
    syzygy_available = os.path.exists(cfg.args.syzygy)

    # Load game_settings
    game_settings = {
        'human_game': False,
        'rotate180': False,
        'use_board_position': False,
        'side_to_move': 'white',
        'time_constraint': 'unlimited',
        'time_total_minutes': 5,
        'time_increment_seconds': 8,
        'chess960': False,
        'enable_syzygy': syzygy_available,
        'book': '',
        'play_white': True,
        '_game_engine': {
            'engine': 'stockfish',
            'Depth': 1,
            'Threads': 1,
            'Contempt': 24,
            'Ponder': False,
            'Skill Level': 20,
            'Strength': 100
        },
        '_analysis_engine': {
            'engine': 'stockfish',
            'Depth': 20,
            'Threads': 1,
            'Contempt': 24,
            'Ponder': False,
        },
        '_led': {
            'thinking': 'center',
        },
    }
    game_settings_filepath = os.path.join(CERTABO_DATA_PATH, 'game_settings.json')
    if not os.path.exists(game_settings_filepath):
        with open(game_settings_filepath, 'w') as f:
            json.dump({}, f)
    with open(game_settings_filepath, 'r') as f:
        saved_game_settings = json.load(f)
        for settings_key in ('_game_engine', '_analysis_engine', '_led'):
            for key, value in saved_game_settings.get(settings_key, {}).items():
                game_settings[settings_key][key] = value

    # Load certabo settings
    certabo_settings = {
        'address_chessboard': None,
        'connection_method': 'usb',
        'remote_control': False,
    }
    certabo_settings_filepath = os.path.join(logger.CERTABO_DATA_PATH, 'certabo_settings.json')
    if not os.path.exists(certabo_settings_filepath):
        with open(certabo_settings_filepath, 'w') as f:
            json.dump(certabo_settings, f)
    with open(certabo_settings_filepath, 'r') as f:
        certabo_settings = json.load(f)

    x, y, left_click = 0, 0, False  # TODO: Check if it can be removed now

    window = "home"  # name of current page
    dialog = ""  # dialog inside the window

    new_setup = True
    start_game = False
    options_menu = None
    connection_button = None

    saved_files = []
    saved_files_time = []
    resume_file_selected = 0
    resume_file_start = 0  # starting filename to show
    engine_choice_menu = None
    book_choice_menu = None

    game_engine = None
    rom = False
    analysis_engine = None
    analysis_request = False
    show_analysis = False
    show_extended_analysis = False

    move = []
    terminal_lines = ["Game started", "Terminal text here"]
    hint_text = ""
    name_to_save = ""

    resuming_new_game = False
    waiting_for_user_move = False
    do_ai_move = False
    do_user_move = False
    banner_certabo_move = False
    banner_fix_pieces = False
    hint_request = False

    chessboard = chess.Board()
    board_state = chessboard.fen()
    starting_position = chess.STARTING_FEN

    pgn_queue = None
    publisher = None

    # ------------- Establish connection
    if cfg.args.usbport is not None:
        certabo_settings['connection_method'] = 'usb'
        certabo_settings['address_chessboard'] = cfg.args.usbport
        last_address_chessboard = None
    elif cfg.args.btport is not None:
        certabo_settings['connection_method'] = 'bluetooth'
        certabo_settings['address_chessboard'] = cfg.args.btport
        last_address_chessboard = None
    else:
        certabo_settings['connection_method'] = certabo_settings.get('connection_method', 'usb')
        last_address_chessboard = certabo_settings.get('address_chessboard', None)
        certabo_settings['address_chessboard'] = None

    last_connection_method = certabo_settings['connection_method']

    chessboard_connection_process = None
    bt_find_address_executor = None
    future_bt_address = None
    connection_button = None
    show_connection_button = time.time() + 3
    while True:
        cfg.scr.fill(COLORS['white'])
        show_sprite("start-up-logo", 7, 0)

        x, y, left_click = check_input_events()

        # If specific address was not given, try to find it
        if certabo_settings['address_chessboard'] is None:
            if certabo_settings['connection_method'] == 'usb':
                certabo_settings['address_chessboard'] = usbtool.find_address(test_address=last_address_chessboard)

            last_address_chessboard = None
            time.sleep(.5)

        # Attempt connection
        if chessboard_connection_process is None and certabo_settings['address_chessboard'] is not None:
            if certabo_settings['connection_method'] == 'usb':
                chessboard_connection_process = usbtool.start_usbtool(certabo_settings['address_chessboard'], separate_process=True)
          
        # Check if expected reading is obtained (future_bt_address should be None by now)
        if (future_bt_address is None) and (not usbtool.QUEUE_FROM_USBTOOL.empty()):
            break

        # If five seconds have elapsed without a successful connection
        # Create and show connection method option button (only if no specific usbport or bt port was given)
        if (cfg.args.usbport is None and cfg.args.btport is None) and (time.time() > show_connection_button):
            if connection_button is None:
                connection_button = media.RadioOption(
                    'Connect via:',
                    certabo_settings, 'connection_method', options=['usb', 'bluetooth'],
                    x0=360, y0=10, x1=340, y1=40, font=cfg.font_large,
                )

            connection_button.draw()
            if left_click:
                connection_button.click(x, y)
                if connection_button.value != last_connection_method:
                    last_connection_method = connection_button.value
                    certabo_settings['remote_control'] = True if connection_button.value == 'bluetooth' else False
                    certabo_settings['address_chessboard'] = None

                    # Close thread and processes that may have started for the other connection_method option
                    if future_bt_address is not None:
                        future_bt_address.cancel()
                        future_bt_address = None
                    if chessboard_connection_process is not None:
                        chessboard_connection_process.kill()
                        chessboard_connection_process = None

        pygame.display.flip()
        time.sleep(.001)

    # Hide connection button
    cfg.scr.fill(COLORS['white'])  # clear screen
    show_sprite("start-up-logo", 7, 0)
    pygame.display.flip()  # copy to screen

    # Save connection method and port
    logging.info(f'Saving Certabo Settings: {certabo_settings}')
    with open(certabo_settings_filepath, 'w') as f:
        json.dump(certabo_settings, f)

    # Initialize modules
    usb_reader = reader_writer.BoardReader(certabo_settings['address_chessboard'])
    usb_reader.ignore_missing = not certabo_settings['remote_control']
    led_manager = reader_writer.LedWriter()
    remote_control = RemoteControl(led_manager, certabo_settings['remote_control'])
    game_clock = GameClock()
    calibration = usb_reader.needs_calibration

    # ------------- Main loop
    if not certabo_settings['connection_method'] == 'bluetooth':
        led_manager.set_leds('all')
        time.sleep(1)  # Time needed to get at least one reading
        led_manager.set_leds()

    poweroff_time = datetime.now()
    if cfg.DEBUG_FPS:
        fps_clock = pygame.time.Clock()
    while True:
        # Close engine process if not in game (or save) window
        if not (window == 'game' or window == 'save'):
            if analysis_engine is not None:
                analysis_engine.kill()
                analysis_engine = None
            if game_engine is not None:
                game_engine.kill()
                game_engine = None

        # Check exit with keyboard or mouse click
        # Get mouse x, y coords and left_click status
        x, y, left_click = check_input_events()

        # Check exit with long click on logo
        if pygame.mouse.get_pressed()[0] and (x < 110) and (y < 101):
            if datetime.now() - poweroff_time >= timedelta(seconds=2):
                do_poweroff(method='logo')
        else:
            poweroff_time = datetime.now()

        # Check exit with remote_control
        board_state = usb_reader.read_board()
        if remote_control.check_exit(board_state, type_='application') == 2:
            do_poweroff(method='remote_control')

        # Reset screen
        cfg.scr.fill(COLORS['white'])
        show_sprite("logo", 8, 6)

        if window == "home":
            if calibration:
                calibration_done = usb_reader.calibration(new_setup, verbose=False)
                led_manager.set_leds('setup')
                if calibration_done:
                    calibration = False
                    led_manager.set_leds()

            window, remote_calibration_request = remote_control.update(window, board_state)
            if remote_calibration_request:
                usb_reader.ignore_missing = True
                calibration = True

            first_button_y = 125
            button_spacing_y = 38
            if dialog != 'calibration':
                new_game_button_area = show_sprite("new_game", 5, first_button_y)
                resume_game_button_area = show_sprite("resume_game", 5, first_button_y + button_spacing_y * 1)
                calibration_button_area = show_sprite("calibration", 5, first_button_y + button_spacing_y * 2)
                options_button_area = show_sprite("options", 5, first_button_y + button_spacing_y * 3)
                play_online_button_area = show_sprite("lichess", 5, first_button_y + button_spacing_y * 4)
            else:
                add_piece_button_area = show_sprite("setup", 5, first_button_y + button_spacing_y * 1)
                setup_button_area = show_sprite("new-setup", 5, first_button_y + button_spacing_y * 2)
                if not calibration:
                    done_button_area = show_sprite('done', 5, first_button_y + button_spacing_y * 4)

            show_board(board_state, rotate=False)
            show_sprite("welcome", 111, 6)
            if calibration:
                show_sprite("please-wait", 253, 170)

            if left_click and not calibration:
                if not dialog == 'calibration':
                    if coords_in(x, y, new_game_button_area):
                        window = "new game"
                        led_manager.set_leds()

                    elif coords_in(x, y, resume_game_button_area):
                        window = "resume"
                        # update saved files list to load
                        files = os.listdir(CERTABO_SAVE_PATH)
                        saved_files = [v for v in files if ".pgn" in v]
                        saved_files_time = [time.gmtime(os.stat(os.path.join(CERTABO_SAVE_PATH, name)).st_mtime) for name in saved_files]
                        terminal_lines = ["", ""]

                    elif coords_in(x, y, calibration_button_area):
                        dialog = 'calibration'

                    elif coords_in(x, y, options_button_area):
                        window = "options"

                    elif coords_in(x, y, play_online_button_area):
                        # Kill usbtool
                        chessboard_connection_process.kill()
                        chessboard_connection_process.join()
                        time.sleep(.750)

                        logging.info('Switching to Online Application')
                        if certabo_settings['connection_method'] == 'bluetooth':
                            args = sys.argv[1:] + ['--btport', certabo_settings['address_chessboard']]
                        else:
                            args = sys.argv[1:] + ['--usbport', certabo_settings['address_chessboard']]
                        if getattr(sys, 'frozen', False):
                            extension = '.exe' if os.name == 'nt' else ''
                            executable = os.path.dirname(sys.executable)
                            executable = os.path.join(executable, f'online{extension}')

                            os.execlp(executable, '"' + executable + '"', *args)  # Hack for windows paths with spaces!
                        else:
                            os.execl(sys.executable, sys.executable, f'online.py', *args)

                # Calibration dialog
                else:
                    if coords_in(x, y, add_piece_button_area):
                        logging.info("Calibration: Add piece - collecting samples")
                        calibration = True
                        new_setup = False
                        calibration_samples = []

                    elif coords_in(x, y, setup_button_area):
                        logging.info("Calibration: New setup - collecting samples")
                        calibration = True
                        new_setup = True
                        calibration_samples = []

                    elif not calibration and coords_in(x, y, done_button_area):
                        dialog = ''

        elif window == "resume":
            show_text("Select game name to resume", 159, 1, COLORS['black'], fontsize='large')
            show_sprite("resume_back", 107, 34)
            show_sprite("resume_game", 263, 283)
            show_sprite("back", 3, 146)
            show_sprite("delete-game", 103, 283)

            pygame.draw.rect(
                cfg.scr,
                COLORS['lightestgrey'],
                (
                    int(113 * cfg.x_multiplier),
                    int(41 * cfg.y_multiplier + resume_file_selected * 29 * cfg.y_multiplier),
                    int(330 * cfg.x_multiplier),
                    int(30 * cfg.y_multiplier),
                ),
            )  # selection

            for i in range(len(saved_files)):
                if i > 7:
                    break
                show_text(saved_files[i + resume_file_start][:-4], 117, 41 + i * 29, COLORS['grey'], fontsize='large')
                v = saved_files_time[i]

                show_text(
                    "%d-%d-%d  %d:%d"
                    % (v.tm_year, v.tm_mon, v.tm_mday, v.tm_hour, v.tm_min),
                    300,
                    41 + i * 29,
                    COLORS['lightgrey'],
                    fontsize='large'
                )

            if dialog == "delete":
                show_sprite("hide_back", 0, 0)
                # TODO: Fix issue here!
                pygame.draw.rect(cfg.scr, COLORS['lightgrey'], (200 + 2, 77 + 2, 220, 78))
                pygame.draw.rect(cfg.scr, COLORS['white'], (200, 77, 220, 78))
                show_text("Delete the game ?", 200 + 32, 67 + 15, COLORS['grey'], fontsize='large')
                show_sprite("back", 200 + 4, 77 + 40)
                show_sprite("confirm", 200 + 4 + 112, 77 + 40)

                if left_click:
                    if (77 + 40 - 5) < y < (77 + 40 + 30):
                        dialog = ""
                        if x > (200 + 105):  # confirm button
                            logging.info("do delete")
                            os.unlink(
                                os.path.join(
                                    CERTABO_SAVE_PATH,
                                    saved_files[resume_file_selected + resume_file_start],
                                )
                            )

                            # update saved files list to load
                            files = os.listdir(CERTABO_SAVE_PATH)
                            saved_files = [v for v in files if ".pgn" in v]
                            saved_files_time = [time.gmtime(os.stat(os.path.join(CERTABO_SAVE_PATH, name)).st_mtime) for name in saved_files]
                            resume_file_selected = 0
                            resume_file_start = 0

            if left_click:

                if 7 < x < 99 and 150 < y < 179:  # back button
                    window = "home"

                if 106 < x < 260 and 287 < y < 317:  # delete button
                    dialog = "delete"  # start delete confirm dialog on the page

                if 107 < x < 442 and 40 < y < 274:  # pressed on file list
                    i = int((int(y) - 41) / 29)
                    if i < len(saved_files):
                        resume_file_selected = i

                if 266 < x < 422 and 286 < y < 316:  # Resume button
                    logging.info("Resuming game")
                    with open(
                            os.path.join(
                                CERTABO_SAVE_PATH,
                                saved_files[resume_file_selected + resume_file_start],
                            ),
                            "r",
                    ) as f:
                        _game = chess.pgn.read_game(f)
                    if _game:
                        chessboard = _game.end().board()
                        _node = _game
                        while _node.variations:
                            _node = _node.variations[0]
                        game_settings['play_white'] = _game.headers["White"] == "Human"
                        starting_position = _game.board().fen()

                        logging.info(f"Resuming game: Move history - {[_move.uci() for _move in _game.mainline_moves()]}")
                        do_ai_move = False
                        do_user_move = False
                        # conversion_dialog = False
                        waiting_for_user_move = False
                        banner_fix_pieces = True
                        resuming_new_game = True
                        window = "new game"

                if 448 < x < 472:  # arrows
                    if 37 < y < 60:  # arrow up
                        if resume_file_start > 0:
                            resume_file_start -= 1
                    elif 253 < y < 284:
                        if (resume_file_start + 8) < len(saved_files):
                            resume_file_start += 1

        elif window == "save":

            show_text("Enter game name to save", 159, 41, COLORS['grey'], fontsize='large')
            show_sprite("terminal", 139, 80)
            show_text(
                name_to_save, 273 - len(name_to_save) * (51 / 10.0), 86, COLORS['terminal_text_color'], fontsize='large'
            )

            # show keyboard
            keyboard_buttons = (
                ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-"),
                ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
                ("a", "s", "d", "f", "g", "h", "j", "k", "l"),
                ("z", "x", "c", "v", "b", "n", "m"),
            )

            lenx = 42  # size of buttons
            leny = 38  # size of buttons

            ky = 128
            x0 = 11

            hover_key = ""

            pygame.draw.rect(
                cfg.scr,
                COLORS['lightgrey'],
                (
                    int(431 * cfg.x_multiplier),
                    int(81 * cfg.y_multiplier),
                    int(lenx * cfg.x_multiplier - 2),
                    int(leny * cfg.y_multiplier - 2),
                ),
            )  # back space
            show_text("<", (431 + 14), (81 + 4), COLORS['black'], fontsize='large')

            for row in keyboard_buttons:
                kx = x0
                for key in row:
                    pygame.draw.rect(
                        cfg.scr,
                        COLORS['lightgrey'],
                        (
                            int(kx * cfg.x_multiplier),
                            int(ky * cfg.y_multiplier),
                            int(lenx * cfg.x_multiplier - 2),
                            int(leny * cfg.y_multiplier - 2),
                        ),
                    )
                    show_text(key, kx + 14, ky + 4, COLORS['black'], fontsize='large')
                    if kx < x < (kx + lenx) and ky < y < (ky + leny):
                        hover_key = key
                    kx += lenx
                ky += leny
                x0 += 20

            pygame.draw.rect(
                cfg.scr,
                COLORS['lightgrey'],
                (
                    int(x0 * cfg.x_multiplier + lenx * cfg.x_multiplier),
                    int(ky * cfg.y_multiplier),
                    int(188 * cfg.x_multiplier),
                    int(leny * cfg.y_multiplier - 2),
                ),
            )  # spacebar
            if (x0 + lenx) < x < (x0 + lenx + 188) and ky < y < (ky + leny):
                hover_key = " "
            show_sprite("save", 388, 264)
            if 388 < x < (388 + 100) and 263 < y < (263 + 30):
                hover_key = "save"
            if 431 < x < (431 + lenx) and 81 < y < (81 + leny):
                hover_key = "<"

                # ----- process buttons -----
            if left_click:

                if hover_key != "":
                    if hover_key == "save":
                        OUTPUT_PGN = os.path.join(
                            CERTABO_SAVE_PATH, "{}.pgn".format(name_to_save)
                        )
                        with open(OUTPUT_PGN, "w") as f:
                            f.write(generate_pgn())
                        window = "game"
                        # banner_do_move = False
                        left_click = False
                        # conversion_dialog = False

                    elif hover_key == "<":
                        if len(name_to_save) > 0:
                            name_to_save = name_to_save[: len(name_to_save) - 1]
                    else:
                        if len(name_to_save) < 22:
                            name_to_save += hover_key

        elif window == "game":
            # Check if exiting game
            # If kings are placed in the central diagonal, skip game logic and eventually exit game into new game
            exit_game_state, remote_hint_request = remote_control.update(window, board_state, game_settings, chessboard)
            if exit_game_state:
                # Countdown until exit
                if exit_game_state == 1:
                    continue
                # Countdown completed
                else:
                    window = 'new game'
                    led_manager.set_leds()

            # Display elements that do not depend on game state
            show_board(chessboard.fen())

            game_overtime = game_clock.update(chessboard)
            game_clock.display()
            show_sprite("terminal", 179, 3)

            show_text(terminal_lines[0], 183, 3, COLORS['terminal_text_color'])
            show_text(terminal_lines[1], 183, 18, COLORS['terminal_text_color'])
            show_text(hint_text, 96, 180 + 27, COLORS['grey'], fontsize='large')

            take_back_button_area = None
            hint_button_area = None
            extended_analysis_button_area = None

            analysis_button_area = show_sprite("analysis", 5, 140 + 100)
            save_button_area = show_sprite("save", 5, 140 + 140)
            exit_button_area = show_sprite("exit", 5 + 80, 140 + 140)

            if not show_extended_analysis:
                if not rom:
                    take_back_button_area = show_sprite("take_back", 5, 140 + 22)

                if not game_settings['human_game'] and not rom:
                    hint_button_area = show_sprite("hint", 5, 140 + 40 + 22)

                if show_analysis:
                    analysis_score = analysis_engine.get_latest_score()
                    show_text(analysis_score, 92, 250, COLORS['grey'])
                    extended_analysis_button_area = create_button('+', 178 - 25, 140 + 100 + 5, color=COLORS['grey'],
                                                                  text_color=COLORS['white'], padding=[0, 5, 0, 5])

            else:
                analysis_engine.plot_extended_analysis(chessboard)
                analysis_score = analysis_engine.get_latest_score(return_incomplete=True)
                show_text(analysis_score, 92, 250, COLORS['grey'])
                extended_analysis_button_area = create_button('x', 178 - 25, 140 + 100 + 5, color=COLORS['grey'],
                                                              text_color=COLORS['white'], padding=[0, 5, 0, 5])

            # Process hint
            if hint_request or remote_hint_request:
                hint_request = False

                logging.info('Getting hint')
                got_polyglot_result = False
                if not game_settings['book']:
                    got_polyglot_result = False
                else:
                    finder = pypolyglot.Finder(game_settings['book'], chessboard, 20)
                    best_move = finder.bestmove()
                    got_polyglot_result = (best_move is not None)

                if got_polyglot_result:
                    hint_text = best_move
                else:
                    proc = stockfish.EngineThread(
                        [_move.uci() for _move in chessboard.move_stack],
                        20,
                        engine=game_settings['_game_engine']['engine'],
                        starting_position=starting_position,
                        chess960=game_settings['chess960'],
                        syzygy_path=cfg.args.syzygy if game_settings['enable_syzygy'] else None,
                    )
                    proc.start()

                    # Display text
                    pygame.draw.rect(cfg.scr, COLORS['lightgrey'], (int(229 * cfg.x_multiplier), int(79 * cfg.y_multiplier),
                                                                    int(200 * cfg.x_multiplier), int(78 * cfg.y_multiplier)))
                    pygame.draw.rect(cfg.scr, COLORS['white'], (int(227 * cfg.x_multiplier), int(77 * cfg.y_multiplier),
                                                                int(200 * cfg.x_multiplier), int(78 * cfg.y_multiplier)))
                    show_text("Analysing...", 227 + 55, 77 + 8, COLORS['grey'], fontsize='large')
                    if not rom:
                        show_sprite("force-move", 247, 77 + 39)

                    got_fast_result = False
                    while proc.is_alive():  # thinking
                        x, y, left_click = check_input_events()

                        # Check if pressed Force move button
                        board_state = usb_reader.read_board(game_settings['rotate180'])
                        force_hint = remote_control.update('thinking', board_state, virtual_board=chessboard)
                        if (left_click and (249 < x < 404) and (120 < y < 149)) or force_hint:
                            proc.stop()
                            proc.join()
                            hint_text = proc.best_move
                            got_fast_result = True
                            logging.info('Forcing hint move')
                            break

                        led_manager.flash_leds(game_settings['_led']['thinking'])
                        # Update timer
                        game_overtime = game_clock.update(chessboard)
                        game_clock.display()
                        pygame.display.flip()
                        time.sleep(.001)

                    if not got_fast_result:
                        hint_text = proc.best_move

                terminal_print(f'hint: {hint_text}')
                logging.info(f'Hint: {hint_text}')
                led_manager.flash_leds(hint_text)
                continue

            # Process analysis
            if analysis_request:
                analysis_request = False

                # Instantiate analysis engine
                if analysis_engine is None:
                    analysis_engine = AnalysisEngine(game_settings['_analysis_engine'])

                # Call new analysis
                analysis_engine.request_analysis(chessboard)
                show_analysis = True

            # Game Logic
            board_state = usb_reader.read_board(game_settings['rotate180'], update=False)

            # If physical board is different than virtual board
            if chessboard.board_fen() != board_state:
                if waiting_for_user_move:
                    move = get_moves(chessboard, board_state, check_double_moves=game_settings['human_game'])

                    if not move:
                        # Check if take back
                        if not rom and is_move_back(chessboard, board_state):
                            logging.info('Implicit take back recognized')
                            take_back_steps()
                            continue

                        highligted_leds = led_manager.highlight_misplaced_pieces(board_state, chessboard, game_settings['rotate180'],
                                                                                 suppress_leds=game_settings['human_game'])
                        if highligted_leds:
                            terminal_print("Invalid move")
                            banner_fix_pieces = True

                    else:  # Move was found
                        waiting_for_user_move = False
                        do_user_move = True

                else:
                    banner_certabo_move = True

            # If physical board is equal to virtual board
            else:
                # LEDS
                # Show leds for king in check
                if chessboard.is_check() and not game_settings['human_game']:
                    # Find king on check
                    checked_king_square = chess.SQUARE_NAMES[chessboard.king(chessboard.turn)]
                    led_manager.set_leds(checked_king_square, game_settings['rotate180'])

                # Show time warning leds
                elif game_clock.time_warning(chessboard) and not game_settings['human_game']:
                    led_manager.flash_leds('corners')

                # Show hint leds
                elif hint_text:
                    led_manager.flash_leds(hint_text)
                # no leds
                else:
                    led_manager.set_leds()

                # Deactivate banners
                banner_certabo_move = False
                banner_fix_pieces = False

                # Set move permissions
                waiting_for_user_move = True
                do_ai_move = False
                if not game_settings['human_game'] and chessboard.turn != game_settings['play_white']:
                    do_ai_move = True
                    waiting_for_user_move = False

            # Update game state (incl. banners and mouse clicks)
            if dialog == "":
                # AI MOVE
                if not game_settings['human_game'] and do_ai_move and not chessboard.is_game_over() and not game_overtime:
                    do_ai_move = False
                    got_polyglot_result = False
                    if not game_settings['book']:
                        got_polyglot_result = False
                    else:
                        finder = pypolyglot.Finder(game_settings['book'], chessboard, game_settings['_game_engine']['Depth'] + 1)
                        best_move = finder.bestmove()
                        got_polyglot_result = (best_move is not None)

                    if got_polyglot_result:
                        ai_move = best_move.lower()
                    else:
                        if game_engine is None:
                            logging.info('Starting Game Engine')
                            game_engine = GameEngine(game_settings['_game_engine'])
                        game_engine.go(chessboard)

                        # Display text
                        pygame.draw.rect(cfg.scr, COLORS['lightgrey'], (int(229 * cfg.x_multiplier), int(79 * cfg.y_multiplier),
                                                                        int(200 * cfg.x_multiplier), int(78 * cfg.y_multiplier)))
                        pygame.draw.rect(cfg.scr, COLORS['white'], (int(227 * cfg.x_multiplier), int(77 * cfg.y_multiplier),
                                                                    int(200 * cfg.x_multiplier), int(78 * cfg.y_multiplier)))
                        show_text("Analysing...", 227 + 55, 77 + 8, COLORS['grey'], fontsize='large')
                        if not rom:
                            show_sprite("force-move", 247, 77 + 39)

                        ai_move_duration = game_clock.sample_ai_move_duration()
                        ai_move_start_time = time.time()
                        waiting_ai_move = True
                        force_ai_move = False
                        while waiting_ai_move or ai_move_start_time + ai_move_duration > time.time():

                            # Event from system & keyboard
                            x, y, left_click = check_input_events()

                            waiting_ai_move = game_engine.waiting_bestmove()

                            # Force move
                            board_state = usb_reader.read_board(game_settings['rotate180'])
                            remote_force_move = remote_control.update('thinking', board_state, virtual_board=chessboard)

                            force_mbutton = left_click and (249 < x < 404) and (120 < y < 149)
                            if remote_force_move or force_mbutton:
                                force_ai_move = True

                            if (not rom and force_ai_move) or game_overtime:
                                if game_engine.interrupt_bestmove():
                                    logging.info('Forcing AI move')
                                    break

                            led_manager.flash_leds(game_settings['_led']['thinking'])
                            game_overtime = game_clock.update(chessboard)
                            game_clock.display()

                            if show_extended_analysis:
                                analysis_engine.plot_extended_analysis(chessboard, clear_previous=True)
                                analysis_score = analysis_engine.get_latest_score(return_incomplete=True)
                                # Clear previous score
                                pygame.draw.rect(cfg.scr, COLORS['white'], (
                                    int(92*cfg.x_multiplier),
                                    int(245*cfg.y_multiplier),
                                    int(60*cfg.x_multiplier),
                                    int(30*cfg.y_multiplier)))
                                show_text(analysis_score, 92, 250, COLORS['grey'])

                            pygame.display.flip()
                            time.sleep(.001)

                        ai_move = str(game_engine.bestmove)

                    if not game_overtime:
                        logging.info(f"AI move: {ai_move}")
                        led_manager.set_leds(ai_move, game_settings['rotate180'])
                        play_audio('move')

                        if not cfg.args.robust:
                            show_board_and_animated_move(chessboard.fen(), ai_move, 178, 40)
                        try:
                            chessboard.push_uci(ai_move)
                            logging.debug(f"after AI move: {chessboard.fen()}")
                            side = ('white', 'black')[int(chessboard.turn)]
                            terminal_print("{} move: {}".format(side, ai_move))
                            if cfg.args.publish:
                                publish()
                        except Exception as e:
                            logging.warning(f"   ----invalid chess_engine move! ---- {ai_move}")
                            logging.warning(f"Exception: {e}")
                            terminal_print(f"Invalid AI move {ai_move}!")

                        if chessboard.is_check():  # AI CHECK
                            terminal_print(" check!", False)

                        if chessboard.is_checkmate():
                            logging.info("mate!")

                        if chessboard.is_stalemate():
                            logging.info("stalemate!")

                # USER MOVE
                if do_user_move and not chessboard.is_game_over() and not game_overtime:
                    do_user_move = False
                    try:
                        for m in move:
                            if not cfg.args.robust:
                                show_board_and_animated_move(chessboard.fen(), m, 178, 40)
                            chessboard.push_uci(m)
                            logging.info(f'User move: {m}')
                            side = ('white', 'black')[int(chessboard.turn)]
                            terminal_print("{} move: {}".format(side, m))
                            hint_text = ""
                            show_analysis = False
                            if cfg.args.publish:
                                publish()
                    except Exception as e:
                        logging.info(f"   ----invalid user move! ---- {move}")
                        logging.exception(f"Exception: {e}")
                        terminal_print(f"Invalid user move {move}!")
                        # waiting_for_user_move = True

                    if chessboard.is_check():
                        terminal_print(" check!", False)

                    if chessboard.is_checkmate():
                        logging.info("mate! we won!")

                    if chessboard.is_stalemate():
                        logging.info("stalemate!")

                # BANNERS
                x0, y0 = 5, 127
                if banner_fix_pieces:
                    show_sprite("place-pieces", x0 + 2, y0 + 2)
                elif banner_certabo_move:
                    show_sprite("move-certabo", x0, y0 + 2)
                elif waiting_for_user_move:
                    show_sprite("do-your-move", x0 + 2, y0 + 2)

                if game_overtime:
                    if game_clock.game_overtime_winner == 1:
                        create_button('White wins', 270, 97, color=COLORS['grey'], text_color=COLORS['white'])
                    else:
                        create_button('Black wins', 270, 97, color=COLORS['grey'], text_color=COLORS['white'])

                elif chessboard.is_game_over():
                    if chessboard.is_checkmate():
                        gameover_banner = "check-mate-banner"
                    elif chessboard.is_stalemate():
                        gameover_banner = "stale-mate-banner"
                    elif chessboard.is_fivefold_repetition():
                        gameover_banner = "five-fold-repetition-banner"
                    elif chessboard.is_seventyfive_moves():
                        gameover_banner = "seventy-five-moves-banner"
                    elif chessboard.is_insufficient_material():
                        gameover_banner = "insufficient-material-banner"
                    show_sprite(gameover_banner, 227, 97)

                # CONVERSION DIALOG
                # if conversion_dialog:
                #     pygame.draw.rect(cfg.scr, COLORS['lightgrey'], (227 + 2, 77 + 2, 200, 78))
                #     pygame.draw.rect(cfg.scr, COLORS['white'], (227, 77, 200, 78))
                #     show_text("Select conversion to:", 227 + 37, 77 + 7, COLORS['grey'])
                #     if game_settings['play_white']:  # show four icons
                #         icons = "white_bishop", "white_knight", "white_queen", "white_rook"
                #         icon_codes = "B", "N", "Q", "R"
                #     else:
                #         icons = "black_bishop", "black_knight", "black_queen", "black_rook"
                #         icon_codes = "b", "n", "q", "r"
                #     i = 0
                #     for icon in icons:
                #         show_sprite(icon, 227 + 15 + i, 77 + 33)
                #         i += 50

                # MOUSE CLICKS
                if left_click:
                    # if conversion_dialog:
                    #     if (227 + 15) < x < (424) and (77 + 33) < y < (77 + 33 + 30):
                    #         i = (x - (227 + 15 - 15)) / 50
                    #         if i < 0:
                    #             i = 0
                    #         if i > 3:
                    #             i = 3
                    #         icon = icon_codes[i]
                    #         if len(move[0]) == 4:
                    #             move[0] += icon
                    #             logging.info(f"move for conversion: {move[0]}", )
                    #             conversion_dialog = False
                    #             do_user_move = True
                    # else:
                    if coords_in(x, y, take_back_button_area):
                        if ((game_settings['human_game'] and len(chessboard.move_stack) >= 1)
                                or (not game_settings['human_game'] and not rom and len(chessboard.move_stack) >= 2)):
                            take_back_steps()
                        else:
                            logging.info(f'Cannot do takeback, move count = {len(chessboard.move_stack)}')

                    elif coords_in(x, y, hint_button_area):
                        hint_request = True

                    elif coords_in(x, y, analysis_button_area):
                        analysis_request = True
                        show_analysis = False

                    elif coords_in(x, y, extended_analysis_button_area):
                        show_extended_analysis = not show_extended_analysis

                    elif coords_in(x, y, save_button_area):
                        window = "save"

                    elif coords_in(x, y, exit_button_area):
                        dialog = "exit"  # start dialog inside Game page

            # Exit dialog
            elif dialog == "exit":
                pygame.draw.rect(cfg.scr, COLORS['lightgrey'], (int(229 * cfg.x_multiplier), int(79 * cfg.y_multiplier),
                                                                int(200 * cfg.x_multiplier), int(78 * cfg.y_multiplier)))
                pygame.draw.rect(cfg.scr, COLORS['white'], (int(227 * cfg.x_multiplier), int(77 * cfg.y_multiplier),
                                                            int(200 * cfg.x_multiplier), int(78 * cfg.y_multiplier)))
                show_text("Save the game or not ?", 227 + 37, 77 + 15, COLORS['grey'])
                show_sprite("save", 238, 77 + 40)
                show_sprite("exit", 238 + 112, 77 + 40)

                if left_click:
                    if (77 + 40 - 5) < y < (77 + 40 + 30):
                        if x > (238 + 105):  # exit button
                            chessboard = chess.Board()
                            dialog = ""
                            window = "home"
                            led_manager.set_leds()
                        else:  # save button
                            dialog = ""
                            window = "save"

        elif window == "new game":
            settings, start_game = remote_control.update(window, board_state, game_settings)

            if dialog == "select time":

                time_total_minutes = game_settings['time_total_minutes']
                time_increment_seconds = game_settings['time_increment_seconds']

                cols = [150, 195]
                rows = [15, 70, 105, 160, 200]

                show_sprite("hide_back", 0, 0)
                create_button("Custom Time Settings", cols[0], rows[0], color=COLORS['green'], text_color=COLORS['white'])
                show_text("Minutes per side:", cols[0], rows[1], COLORS['black'], fontsize='large')
                minutes_button_area = create_button('{}'.format(time_total_minutes), cols[1], rows[2], color=COLORS['grey'], text_color=COLORS['white'])
                minutes_less_button_area = create_button("<", minutes_button_area[0] - 5, rows[2], text_color=COLORS['grey'], color=COLORS['white'], align='right',
                                                         padding=(5, 2, 5, 2))
                minutes_less2_button_area = create_button("<<", minutes_less_button_area[0] - 5, rows[2], text_color=COLORS['grey'], color=COLORS['white'],
                                                          align='right',
                                                          padding=(5, 0, 5, 0))
                minutes_more_button_area = create_button(">", minutes_button_area[2] + 5, rows[2], text_color=COLORS['grey'], color=COLORS['white'],
                                                         padding=(5, 2, 5, 2))
                minutes_more2_button_area = create_button(">>", minutes_more_button_area[2] + 5, rows[2], text_color=COLORS['grey'], color=COLORS['white'],
                                                          padding=(5, 0, 5, 0))

                show_text("Increment in seconds:", cols[0], rows[3], COLORS['black'], fontsize='large')
                seconds_button_area = create_button('{}'.format(time_increment_seconds), cols[1], rows[4], color=COLORS['grey'], text_color=COLORS['white'])
                seconds_less_button_area = create_button("<", seconds_button_area[0] - 5, rows[4], text_color=COLORS['grey'], color=COLORS['white'], align='right',
                                                         padding=(5, 2, 5, 2))
                seconds_less2_button_area = create_button("<<", seconds_less_button_area[0] - 5, rows[4], text_color=COLORS['grey'], color=COLORS['white'],
                                                          align='right',
                                                          padding=(5, 0, 5, 0))
                seconds_more_button_area = create_button(">", seconds_button_area[2] + 5, rows[4], text_color=COLORS['grey'], color=COLORS['white'],
                                                         padding=(5, 2, 5, 2))
                seconds_more2_button_area = create_button(">>", seconds_more_button_area[2] + 5, rows[4], text_color=COLORS['grey'], color=COLORS['white'],
                                                          padding=(5, 0, 5, 0))
                done_button_area = create_button("Done", 415, 275, color=COLORS['darkergreen'], text_color=COLORS['white'])

                if left_click:
                    if coords_in(x, y, minutes_less_button_area):
                        time_total_minutes -= 1
                    elif coords_in(x, y, minutes_less2_button_area):
                        time_total_minutes -= 10
                    elif coords_in(x, y, minutes_more_button_area):
                        time_total_minutes += 1
                    elif coords_in(x, y, minutes_more2_button_area):
                        time_total_minutes += 10
                    elif coords_in(x, y, seconds_less_button_area):
                        time_increment_seconds -= 1
                    elif coords_in(x, y, seconds_less2_button_area):
                        time_increment_seconds -= 10
                    elif coords_in(x, y, seconds_more_button_area):
                        time_increment_seconds += 1
                    elif coords_in(x, y, seconds_more2_button_area):
                        time_increment_seconds += 10

                    game_settings['time_total_minutes'] = max(time_total_minutes, 1)
                    game_settings['time_increment_seconds'] = max(time_increment_seconds, 0)

                    if coords_in(x, y, done_button_area):
                        dialog = ""
            elif dialog == "select_engine":
                if engine_choice_menu is None:
                    engine_choice_menu = media.ListOption(
                        'Select game engine:',
                        game_settings['_game_engine'], 'engine', get_engine_list(),
                        x0=160, y0=20, x1=160, y1=50, font=cfg.font_large
                    )
                engine_choice_menu.draw()
                if left_click:
                    engine_choice_menu.click(x, y)
                    if not engine_choice_menu.open:
                        dialog = ''
            elif dialog == "select_book":
                if book_choice_menu is None:
                    book_choice_menu = media.ListOption(
                        'Select book:',
                        game_settings, 'book', get_book_list(),
                        x0=160, y0=20, x1=160, y1=50, font=cfg.font_large,
                        null_value=''
                    )
                book_choice_menu.draw()
                if left_click:
                    book_choice_menu.click(x, y)
                    if not book_choice_menu.open:
                        dialog = ''
            else:
                cols = [20, 150, 190, 280, 460]
                rows = [15, 60, 105, 150, 195, 225, 255, 270]

                txt_x, _ = show_text("Mode:", cols[1], rows[0] + 5, COLORS['grey'], fontsize='large')
                human_game_button_area = create_button(
                    "Human",
                    txt_x + 15,
                    rows[0],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if game_settings['human_game'] else COLORS['lightgrey'],
                )
                _, _, human_game_button_x, _ = human_game_button_area
                computer_game_button_area = create_button(
                    "Engine",
                    human_game_button_x + 5,
                    rows[0],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if not game_settings['human_game'] else COLORS['lightgrey'],
                )
                _, _, computer_game_button_x, _ = computer_game_button_area
                flip_board_button_area = create_button(
                    "Flip board",
                    computer_game_button_x + 5,
                    rows[0],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if game_settings['rotate180'] else COLORS['lightgrey'],
                )
                use_board_position_button_area = create_button(
                    "Use board position",
                    cols[1],
                    rows[1],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if game_settings['use_board_position'] else COLORS['lightgrey'],
                )
                txt_x, _ = show_text("Time:", cols[1], rows[2] + 5, COLORS['grey'], fontsize='large')

                time_constraint = game_settings['time_constraint']
                time_unlimited_button_area = create_button(
                    u"\u221E",
                    txt_x + 5,
                    rows[2],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if time_constraint == 'unlimited' else COLORS['lightgrey'],
                    padding=(5, 10, 5, 10)
                )
                h_gap = 4
                time_blitz_button_area = create_button(
                    "5+0",
                    time_unlimited_button_area[2] + h_gap,
                    rows[2],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if time_constraint == 'blitz' else COLORS['lightgrey'],
                )
                time_rapid_button_area = create_button(
                    "10+0",
                    time_blitz_button_area[2] + h_gap,
                    rows[2],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if time_constraint == 'rapid' else COLORS['lightgrey'],
                )
                time_classical_button_area = create_button(
                    "15+15",
                    time_rapid_button_area[2] + h_gap,
                    rows[2],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if time_constraint == 'classical' else COLORS['lightgrey'],
                )

                time_custom_button_area = create_button(
                    "Other",
                    time_classical_button_area[2] + h_gap,
                    rows[2],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if time_constraint == 'custom' else COLORS['lightgrey'],
                )

                chess960_button_area = create_button(
                    "Chess960",
                    cols[1],
                    rows[3],
                    text_color=COLORS['white'],
                    color=COLORS['darkergreen'] if game_settings['chess960'] else COLORS['lightgrey'],
                )

                if syzygy_available:
                    syzygy_button_area = create_button(
                        "Syzygy",
                        chess960_button_area[2] + 5,
                        rows[3],
                        text_color=COLORS['white'],
                        color=COLORS['darkergreen'] if game_settings['enable_syzygy'] else COLORS['lightgrey'],
                    )

                if game_settings['use_board_position']:
                    _, _, use_board_position_button_x, _ = use_board_position_button_area
                    side_to_move_button_area = create_button(
                        "White to move" if game_settings['side_to_move'] == "white" else "Black to move",
                        use_board_position_button_x + 5,
                        rows[1],
                        text_color=COLORS['white'] if game_settings['side_to_move'] == 'black' else COLORS['black'],
                        color=COLORS['black'] if game_settings['side_to_move'] == 'black' else COLORS['lightestgrey'],
                    )
                else:
                    side_to_move_button_area = None
                if game_settings['human_game']:
                    depth_less_button_area = None
                    depth_more_button_area = None
                else:
                    engine_repr = game_settings['_game_engine']['engine']
                    if len(engine_repr) > 20:
                        engine_repr = f"{engine_repr[:20]}..."
                    show_text(f"Engine: {engine_repr}", cols[1], rows[4] + 5, COLORS['grey'], fontsize='large')
                    select_engine_button_area = create_button(
                        '...',
                        cols[-1],
                        rows[4],
                        text_color=COLORS['white'],
                        color=COLORS['darkergreen'],
                        padding=(0, 5, 0, 5),
                        align='right'
                    )

                    book_repr = game_settings['book']
                    if len(book_repr) > 20:
                        book_repr = f"{book_repr[:20]}..."
                    _, _ = show_text(f"Book: {book_repr}", cols[1], rows[5] + 5, COLORS['grey'], fontsize='large')
                    select_book_button_area = create_button(
                        '...',
                        cols[-1],
                        rows[5],
                        text_color=COLORS['white'],
                        color=COLORS['darkergreen'],
                        padding=(0, 5, 0, 5),
                        align='right'
                    )

                    txt_x, _ = show_text("Depth:", cols[0], rows[4] + 8, COLORS['grey'])
                    difficulty_button_area = create_button('{:02d}'.format(game_settings['_game_engine']['Depth']), cols[0] + 20, rows[5], color=COLORS['green'],
                                                           text_color=COLORS['white'])
                    depth_less_button_area = create_button("<", difficulty_button_area[0] - 5, rows[5], text_color=COLORS['white'],
                                                           color=COLORS['lightgrey'], align='right')
                    depth_more_button_area = create_button(">", difficulty_button_area[2] + 5, rows[5], text_color=COLORS['white'],
                                                           color=COLORS['lightgrey'])

                    x0 = txt_x + 5
                    y0 = rows[4] + 8
                    if not game_settings['human_game']:
                        if game_settings['_game_engine']['Depth'] == 1:
                            difficulty_label = 'Easiest'
                        elif game_settings['_game_engine']['Depth'] < 5:
                            difficulty_label = 'Easy'
                        elif game_settings['_game_engine']['Depth'] > 19:
                            difficulty_label = 'Hardest'
                        elif game_settings['_game_engine']['Depth'] > 10:
                            difficulty_label = 'Hard'
                        else:
                            difficulty_label = 'Normal'
                        show_text(difficulty_label, x0, y0, COLORS['green'])

                if not game_settings['human_game']:
                    txt_x, _ = show_text("Play as:", cols[1], rows[6] + 5, COLORS['green'], fontsize='large')
                    sprite_color = "black"
                    if game_settings['play_white']:
                        sprite_color = "white"
                    color_button_area = show_sprite(sprite_color, txt_x + 5, rows[6])

                done_button_area = show_sprite("back", cols[0], rows[-1])
                start_button_area = show_sprite("start", cols[-1] - 100, rows[-1])

                if left_click:
                    if coords_in(x, y, human_game_button_area):
                        game_settings['human_game'] = True
                    if coords_in(x, y, computer_game_button_area):
                        game_settings['human_game'] = False
                    if coords_in(x, y, flip_board_button_area):
                        game_settings['rotate180'] = not game_settings['rotate180']
                    if coords_in(x, y, use_board_position_button_area):
                        game_settings['use_board_position'] = not game_settings['use_board_position']
                    for time_button, time_string in zip((time_unlimited_button_area, time_blitz_button_area,
                                                         time_rapid_button_area, time_classical_button_area),
                                                        ('unlimited', 'blitz', 'rapid', 'classical')):
                        if coords_in(x, y, time_button):
                            game_settings['time_constraint'] = time_string
                    if coords_in(x, y, time_custom_button_area):
                        dialog = "select time"
                        game_settings['time_constraint'] = 'custom'
                    if coords_in(x, y, chess960_button_area):
                        game_settings['chess960'] = not game_settings['chess960']
                    if syzygy_available and coords_in(x, y, syzygy_button_area):
                        game_settings['enable_syzygy'] = not game_settings['enable_syzygy']
                    if coords_in(x, y, depth_less_button_area):
                        if game_settings['_game_engine']['Depth'] > 1:
                            game_settings['_game_engine']['Depth'] -= 1
                        else:
                            game_settings['_game_engine']['Depth'] = cfg.args.max_depth
                    if coords_in(x, y, depth_more_button_area):
                        if game_settings['_game_engine']['Depth'] < cfg.args.max_depth:
                            game_settings['_game_engine']['Depth'] += 1
                        else:
                            game_settings['_game_engine']['Depth'] = 1
                    if game_settings['use_board_position']:
                        if coords_in(x, y, side_to_move_button_area):
                            game_settings['side_to_move'] = 'white' if game_settings['side_to_move'] == 'black' else 'black'
                    if coords_in(x, y, select_engine_button_area):
                        dialog = "select_engine"
                        current_engine_page = 0
                    if coords_in(x, y, select_book_button_area):
                        dialog = "select_book"

                    if coords_in(x, y, color_button_area):
                        game_settings['play_white'] = not game_settings['play_white']

                    if coords_in(x, y, done_button_area):
                        window = "home"

                    if coords_in(x, y, start_button_area):
                        start_game = True

            # Initialize game settings
            if start_game:
                logging.info('Starting game')
                start_game = False
                window = "game"
                if resuming_new_game:
                    resuming_new_game = False
                else:
                    if not game_settings['use_board_position']:
                        chessboard = chess.Board()
                        starting_position = chessboard.fen()
                    else:
                        chessboard = chess.Board(fen=board_state.split()[0],
                                                 chess960=game_settings['chess960'])
                        chessboard.turn = game_settings['side_to_move'] == 'white'
                        chessboard.set_castling_fen('KQkq')
                        starting_position = chessboard.fen()
                        if (not chessboard.status() == chess.STATUS_VALID
                                and chessboard.status() != chess.STATUS_BAD_CASTLING_RIGHTS):
                            logging.warning('Board position is not valid')
                            logging.warning(f'{chessboard.status().__repr__()}')
                            print('Board position is not valid')
                            print(chessboard.status())
                            window = 'new game'
                            continue

                rom = game_settings['_game_engine']['engine'].startswith('rom')
                if rom:
                    game_engine = RomEngine(depth=game_settings['_game_engine']['Depth'] + 1, rom=game_settings['_game_engine']['engine'].replace('rom-', ''))

                # conversion_dialog = False
                do_user_move = False
                do_ai_move = False
                waiting_for_user_move = False
                banner_fix_pieces = True
                hint_request = False
                analysis_request = False
                show_analysis = False
                show_extended_analysis = False

                terminal_lines = ["", ""]
                hint_text = ""
                game_clock.start(chessboard, game_settings)
                if cfg.args.publish:
                    make_publisher()

        # TODO: Print version date in options
        elif window == "options":
            if options_menu is None:
                class OptionsMenu:
                    def __init__(self):
                        self.dialog_button = media.RadioOption('Settings', {'dialog': 'Game Engine'}, 'dialog', options=['Game Engine', 'Analysis Engine', 'Chessboard'],
                                                               y0=145, x1=10, y1=170, vertical=True, font=cfg.font_large)
                        self.active_buttons = []

                        cols = [160, 235, 270, 380]
                        rows = [0, 35, 70, 105, 140, 175, 225, 260]

                        engine_settings = game_settings['_game_engine']
                        self.game_engine_buttons = [
                            media.RangeOption('Depth:', engine_settings, 'Depth', min_=1, max_=20, x0=cols[0], x1=cols[2], y1=rows[1]),
                            media.RangeOption('Threads:', engine_settings, 'Threads', min_=1, max_=512, x0=cols[0], x1=cols[2], y1=rows[2]),
                            media.RangeOption('Contempt:', engine_settings, 'Contempt', min_=-100, max_=100, x0=cols[0], x1=cols[2], y1=rows[3]),
                            media.RadioOption('Ponder:', engine_settings, 'Ponder', options=[True, False], x0=cols[0], x1=cols[1], y1=rows[4]),

                            media.RangeOption('Skill Level:', engine_settings, 'Skill Level', min_=0, max_=20, x0=cols[0], x1=cols[2], y1=rows[5], subtitle='(Stockfish & Lc0)'),
                            media.RangeOption('Strength:', engine_settings, 'Strength', min_=0, max_=100, x0=cols[0], x1=cols[2], y1=rows[6], subtitle='(Houdini)'),
                        ]

                        cols = [160, 235, 270]
                        rows = [0, 35, 70, 105, 140]

                        engines_available = ['stockfish']
                        if 'lc0' in get_engine_list():
                            engines_available.append('lc0')
                        engine_settings = game_settings['_analysis_engine']
                        self.game_analysis_buttons = [
                            media.RadioOption('Engine:', engine_settings, 'engine', options=engines_available, x0=cols[0], x1=cols[1], y1=rows[1]),
                            media.RangeOption('Depth:', engine_settings, 'Depth', min_=1, max_=20, x0=cols[0], x1=cols[2], y1=rows[2]),
                            media.RangeOption('Threads:', engine_settings, 'Threads', min_=1, max_=128, x0=cols[0], x1=cols[2], y1=rows[3]),
                            media.RangeOption('Contempt:', engine_settings, 'Contempt', min_=-100, max_=100, x0=cols[0], x1=cols[2], y1=rows[4]),
                        ]

                        self.certabo_settings_buttons = [
                            media.RadioOption('Remote control:', certabo_settings, 'remote_control', options=[True, False],
                                              x0=cols[0], x1=cols[2], y1=rows[1]),
                            media.RadioOption('AI Thinking leds:', game_settings['_led'], 'thinking', options=['center', 'corner', 'none'],
                                              x0=cols[0], x1=cols[2], y1=rows[2])
                        ]

                    def show(self):
                        self.dialog_button.draw()
                        if self.dialog_button.value == 'Game Engine':
                            self.active_buttons = self.game_engine_buttons
                        elif self.dialog_button.value == 'Analysis Engine':
                            self.active_buttons = self.game_analysis_buttons
                        elif self.dialog_button.value == 'Chessboard':
                            self.active_buttons = self.certabo_settings_buttons

                        for button in self.active_buttons:
                            button.draw()

                options_menu = OptionsMenu()

            options_menu.show()
            done_button_area = show_sprite('done', 5, 277)

            if left_click:
                if options_menu.dialog_button.click(x, y):
                    continue

                for button in options_menu.active_buttons:
                    clicked = button.click(x, y)
                    if clicked:
                        break

                if coords_in(x, y, done_button_area):
                    dialog = ""
                    window = "home"

                    # Save settings
                    with open(game_settings_filepath, 'w') as f:
                        json.dump({'_game_engine': game_settings['_game_engine'],
                                   '_analysis_engine': game_settings['_analysis_engine'],
                                   '_led': game_settings['_led']}, f)

                    with open(certabo_settings_filepath, 'w') as f:
                        json.dump(certabo_settings, f)
                        remote_control.on = certabo_settings['remote_control']

        if cfg.DEBUG_FPS:
            fps_clock.tick()
            fps = fps_clock.get_fps()
            show_text(f'FPS = {fps:.1f}', 5, 5, color=COLORS['black'])

        pygame.display.flip()
        time.sleep(.001)

        if window != "home":
            usb_reader.ignore_missing = True
