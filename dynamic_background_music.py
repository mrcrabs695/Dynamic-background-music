"""
Python application made to replicate the opera gx dynamic background music.

this will not be entirely accurate to opera gx's version, as i am limited to using segments of the full music file instead of dynamically combining 
the individual instruments or however opera gx does it
"""

import pynput
import traceback
import sys
from time import sleep, time
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRunnable, Signal, Slot, QObject, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QGridLayout, QVBoxLayout, QLabel, QPushButton, QWidget, QSlider
from PySide6.QtGui import QIcon
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

class ThreadManager(QObject):
    threadpool = QThreadPool()
thread_manager = ThreadManager()


class Player(QMediaPlayer):
    def __init__(self):
        super().__init__()
        
        self.audio_output = QAudioOutput()
        self.current_volume = self.audio_output.volume()
        
        self.setAudioOutput(self.audio_output)
        self.setSource("OperaMusic.mp3")
        self.setLoops(1000)
        
        self.fade_in = QPropertyAnimation(self.audio_output, b"volume")
        self.fade_in.setDuration(1000)
        self.fade_in.setStartValue(0.01)
        self.fade_in.setEndValue(self.current_volume)
        self.fade_in.setEasingCurve(QEasingCurve.Type.Linear)
        self.fade_in.setKeyValueAt(0.01, 0.01)
        
        self.fade_out = QPropertyAnimation(self.audio_output, b"volume")
        self.fade_out.setDuration(1000)
        self.fade_out.setStartValue(self.current_volume)
        self.fade_out.setEndValue(0)
        self.fade_out.setEasingCurve(QEasingCurve.Type.Linear)
        self.fade_out.setKeyValueAt(0.01, self.current_volume)
        self.fade_out.finished.connect(self.pause)
        
        self.fade_in_time = 1000
        self.fade_out_time = 1000
    
    def play_fade_in(self):
        self.fade_in.setDuration(self.fade_in_time)
        self.audio_output.setVolume(0.01)
        self.fade_in.setEndValue(self.current_volume)
        self.play()
        sleep(0.1)
        self.fade_in.start()
    def pause_fade_out(self):
        self.fade_out.setDuration(self.fade_out_time)
        self.current_volume = self.audio_output.volume()
        self.fade_out.setStartValue(self.current_volume)
        self.fade_out.setKeyValueAt(0.01, self.current_volume)
        self.fade_out.start()


class AudioSubChunk:
    def __init__(self, start_time:float, end_time:float, loop_start:bool = False, loop_end:bool = False, transition:str = "0-0"):
        self.start_time = start_time
        self.end_time = end_time
        self.loop_start = loop_start
        self.loop_end = loop_end
        self.transition = transition

class AudioChunk:
    def __init__(self, start_time:float, end_time:float, intensity_start:float, intensity_end:float, subchunks:dict):
        #* each chunk must have AT LEAST a start and an end subchunk, transition chunks are optional
        self.start_time = start_time
        self.end_time = end_time
        self.intensity_start = intensity_start
        self.intensity_end = intensity_end
        
        #? i have subchunks so its smoother to transition between different activity levels
        self.subchunks = subchunks
        
        for subchunk in subchunks:
            if subchunk.loop_start:
                self.loop_start = subchunk
            if subchunk.loop_end:
                self.loop_end = subchunk


    def __str__(self):
        return f"active_needed: {self.intensity_start} - start_time: {self.start_time} - chunk_count: {len(self.subchunks)}"


class WorkerSignals(QObject):
    result = Signal(object)
    finished = Signal()
    error = Signal(str)

class KeyPressThread(QRunnable):
    signals = WorkerSignals()
    
    @Slot()
    def run(self):
        print("run")
        def on_key_release(key):
            self.signals.result.emit(key)
        with pynput.keyboard.Listener(on_release=on_key_release) as listener:
            try:
                listener.join()
            except:
                self.signals.error.emit(traceback.format_exc())

class DynamicAudioPlayer(QObject):
    primary_player_pos_changed = Signal(float)
    
    def __init__(self, *args, **kwargs):
        super().__init__(args, kwargs)
        self.audio_chunks = {
            "low activity 1": AudioChunk(0.0, 41.6, 0, 5, {
                "start chunk": AudioSubChunk(0.0, 5.0),
                "chunk 2": AudioSubChunk(5.0, 10.6, True),
                "chunk 3": AudioSubChunk(10.6, 16.2),
                "chunk 4": AudioSubChunk(16.2, 21.8),
                "chunk 5": AudioSubChunk(21.8, 27.1),
                "chunk 6": AudioSubChunk(27.1, 34.6),
                "end chunk": AudioSubChunk(34.6, 41.6, loop_end=True),
            }),
            
            "medium activity 1": AudioChunk(41.6, 70.0, 5, 15, {
                "start chunk": AudioSubChunk(41.6, 48.1, True),
                "chunk 2": AudioSubChunk(48.1, 55.4),
                "chunk 3": AudioSubChunk(55.4, 59.2),
                "chunk 4": AudioSubChunk(59.2, 65.8),
                "end chunk": AudioSubChunk(65.8, 70.0, loop_end=True),
            }),
            
            #? the chunks here use 2 decimal points for smoother transitions
            "high activity 1": AudioChunk(70.0, 108.4, 15, 20, {
                "start chunk": AudioSubChunk(70.0, 75.66),
                "chunk 2": AudioSubChunk(75.66, 77.73, True),
                "chunk 3": AudioSubChunk(77.73, 81.12),
                "chunk 4": AudioSubChunk(81.12, 86.17),
                "chunk 5": AudioSubChunk(86.17, 89.31),
                "chunk 6": AudioSubChunk(89.31, 92.04),
                "chunk 7": AudioSubChunk(92.04, 95.45),
                "chunk 8": AudioSubChunk(95.45, 100.21),
                "chunk 9": AudioSubChunk(100.21, 105.64),
                "end chunk": AudioSubChunk(105.64, 108.4, loop_end=True)
            }),
        }
        
        self._player_1 = Player()
        self._player_2 = Player()
        self._current_key_presses = 0 #? key presses per second
        self._last_kps = 0
        self._kps = 0
        self._last_keypress = time()
        
        self.primary_player = self._player_1
        self.secondary_player = self._player_2
        self.current_chunk = "low activity 1"
        self.current_subchunk = "start chunk"
        self.set_player_pos(self.primary_player, self.audio_chunks[self.current_chunk].start_time)
        self.primary_player.positionChanged.connect(self.emit_primary_player_pos_changed)
        self.primary_player_pos_changed.connect(self.set_current_chunk)
        
        self.music_intensity = 0.0
        self.average_kps = 0
        
        self.chunk_to_transition_to = None
        self.is_transitioning = False
        
        self.update_activity = QTimer()
        self.update_activity.setInterval(1000)
        self.update_activity.timeout.connect(self.decay_music_intensity)
        self.update_activity.start()
        
        self.transition_timeout = QTimer()
        self.transition_timeout.setInterval(5000)
        self.transition_timeout.setSingleShot(True)
        self.transition_timeout.timeout.connect(self.not_transitioning)
        
        self.primary_player.play_fade_in()
        
    #? util functions to translate the time differences between the media player and the defined audio chunks
    def set_player_pos(self, player:Player, pos:float):
        player.setPosition(int(pos * 1000))

    def player_pos(self, player:Player):
        return player.position() / 1000
    
    def emit_primary_player_pos_changed(self, pos:int):
        self.primary_player_pos_changed.emit(pos / 1000)
    ###
        
    def increase_music_intensity(self):
        if self.average_kps > 6 and self.music_intensity < 20:
            self.music_intensity += 2
        elif self.music_intensity < 20:
            self.music_intensity += 1
    
    def decay_music_intensity(self):
        if self.music_intensity > 0 and self._last_keypress + 5 < time():
            self.music_intensity -= 4
    
    def calculate_activity(self, key):
        self._current_key_presses += 1
        if self._last_keypress + 1 < time():
            self._kps = self._current_key_presses
            self._current_key_presses = 0
            self._last_kps = self._kps
            self.average_kps = int((self._last_kps + self._kps) / 2)
            self._last_keypress = time()
            
        self.increase_music_intensity()
    
    def set_current_chunk(self, current_duration:float):
        current_chunk = None
        current_subchunk = None
        for chunk_name, chunk in self.audio_chunks.items():
            if current_duration > chunk.start_time and current_duration < chunk.end_time:
                current_chunk = chunk_name
                
                for subchunk_name, subchunk in chunk.subchunks.items():
                    if current_duration > subchunk.start_time and current_duration < subchunk.end_time:
                        current_subchunk = subchunk_name
        if current_chunk != None:
            self.current_chunk = current_chunk
            self.current_subchunk = current_subchunk
        # print(f"current chunk: {self.current_chunk}")
        # print(f"current subchunk: {self.current_subchunk}")
        
    def not_transitioning(self):
            self.is_transitioning = False
        
    def transition(self, start_chunk:AudioChunk|AudioSubChunk, current_duration:float, end_chunk:AudioChunk|AudioSubChunk):
        if self.is_transitioning:
            return
        print("transition time!")
        print(f"start chunk: {start_chunk}")
        print(f"current position: {current_duration}")
        print(f"end chunk: {end_chunk}")
        self.is_transitioning = True
        
        self.primary_player.pause_fade_out()
        self.set_player_pos(self.secondary_player, end_chunk.start_time)
        self.secondary_player.play_fade_in()
        new_primary_player = self.secondary_player
        new_secondary_player = self.primary_player
        self.primary_player = new_primary_player
        self.secondary_player = new_secondary_player
        self.transition_timeout.start()
        
    

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.player = Player()
        # setting up actions
        self.play_icon = QIcon.fromTheme("media-playback-start")
        self.play_action = self.addAction(self.play_icon, "Play")
        self.play_action.triggered.connect(self.player.play_fade_in)
        
        self.pause_icon = QIcon.fromTheme("media-playback-pause")
        self.pause_action = self.addAction(self.pause_icon, "Pause")
        self.pause_action.triggered.connect(self.player.pause_fade_out)
        
    def setup_widgets(self):
        # configure volume slider
        available_width = self.screen().availableGeometry().width()
        self.volume_slider = QSlider()
        self.volume_slider.setOrientation(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setMinimumWidth(int(available_width / 20))
        self.volume_slider.setMaximumWidth(int(available_width / 15))
        
        self.volume_label = QLabel()
        self.volume_label.setText("Volume:")
        
        self.current_volume_label = QLabel()
        self.player.audio_output.volumeChanged.connect(lambda vol: self.current_volume_label.setText(str(int(vol * 100))))
        
        #* have to times the audio volume by 100 as it outputs as a float with a value between 0.0 and 1.0
        self.volume_slider.setValue(int(self.player.audio_output.volume() * 100))
        self.volume_slider.setTickInterval(10)
        self.volume_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.valueChanged.connect(lambda value: self.player.audio_output.setVolume(float(value / 100)))
        self.volume_slider.valueChanged.connect(lambda value: self.set_current_vol(float(value / 100)))
        
        # setting up play button
        self.play_button = QPushButton()
        self.play_button.setIcon(self.play_icon)
        self.play_button.setCheckable(True)
        self.play_button.toggled.connect(self.play_button_switch)
        
        layout = QVBoxLayout()
        container = QWidget()
        layout.addWidget(self.play_button)
        layout.addWidget(self.volume_label)
        layout.addWidget(self.current_volume_label)
        layout.addWidget(self.volume_slider)
        container.setLayout(layout)
        self.setCentralWidget(container)
        
    def play_button_switch(self, checked):
        if checked:
            self.play_button.setIcon(self.pause_icon)
            self.pause_action.trigger()
        elif not checked:
            self.play_button.setIcon(self.play_icon)
            self.play_action.trigger()
            
    def set_current_vol(self, vol):
        self.player.current_volume = vol



app = QApplication(sys.argv)
title = "OpGX dynamic music player"
test = DynamicAudioPlayer()
key_press_thread = KeyPressThread()
key_press_thread.signals.result.connect(test.calculate_activity)
thread_manager.threadpool.start(key_press_thread)


# main_window = MainWindow()
# app.setApplicationName(title)
# main_window.setWindowTitle(title)
# main_window.setup_widgets()
# main_window.show()
    
sys.exit(app.exec())
