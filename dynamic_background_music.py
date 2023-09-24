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
    def __init__(self, start_time:float, end_time:float, activity_needed:int, subchunks:dict):
        #* each chunk must have AT LEAST a start and an end subchunk, transition chunks are optional
        self.start_time = start_time
        self.end_time = end_time
        self.activity_needed = activity_needed
        
        #? i have subchunks so its smoother to transition between different activity levels
        self.subchunks = subchunks


    def __str__(self):
        return f"active_needed: {self.activity_needed} - start_time: {self.start_time} - chunk_count: {len(self.subchunks)}"


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
                self.signals.error.emit(traceback.print_exc())

class DynamicAudioPlayer:
    def __init__(self):
        self.audio_chunks = {
            "low activity 1": AudioChunk(0.0, 41.6, 0, {
                "start chunk": AudioSubChunk(0.0, 5.0),
                "chunk 2": AudioSubChunk(5.0, 10.6, True),
                "chunk 3": AudioSubChunk(10.6, 16.2),
                "chunk 4": AudioSubChunk(16.2, 21.8),
                "chunk 5": AudioSubChunk(21.8, 27.1),
                "chunk 6": AudioSubChunk(27.1, 34.6),
                "end chunk": AudioSubChunk(34.6, 41.6, loop_end=True),
            }),
            
            "medium activity 1": AudioChunk(41.6, 70.0, 1, {
                "start chunk": AudioSubChunk(41.6, 48.1, True),
                "chunk 2": AudioSubChunk(48.1, 55.4),
                "chunk 3": AudioSubChunk(55.4, 59.2),
                "chunk 4": AudioSubChunk(59.2, 65.8),
                "end chunk": AudioSubChunk(65.8, 70.0, loop_end=True),
            }),
            
            #? the chunks here use 2 decimal points for smoother transitions
            "high activity 1": AudioChunk(70.0, 108.4, 2, {
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
        self.primary_player = self._player_1
        self.secondary_player = self._player_2
        
        self.activity = 0
        self.last_activity = 0
        self.music_intensity = 0
        self.current_key_presses = 0 #? key presses per second
        self.last_kps = 0
        self.kps = 0
        self.average_kps = 0
        self.last_keypress = time()
        
        self.current_chunk = "low activity 1"
        self.current_subchunk = "start chunk"
        self.chunk_to_transition_to = None
        self.is_transitioning = False
        
        self.update_activity_timer = QTimer()
        self.update_activity_timer.setInterval(1000)
        self.update_activity_timer.timeout.connect(self.calculate_activity)
        self.update_activity_timer.timeout.connect(self.check_activity)
        self.update_activity_timer.start()
        self.transition_timeout = QTimer()
        self.transition_timeout.setInterval(5000)
        self.transition_timeout.setSingleShot(True)
        self.primary_player.positionChanged.connect(self.set_current_chunk)
        self.primary_player.play_fade_in()
        
    def calculate_kps(self, key):
        self.current_key_presses = self.current_key_presses + 1
    
    def calculate_average_kps(self):
        self.average_kps = int((self.last_kps + self.kps) / 2)
    
    def calculate_activity(self):
        if self.average_kps >= 0:
            self.last_activity = self.activity
            self.activity = 0
        if self.average_kps >= 3:
            self.last_activity = self.activity
            self.activity = 1
        if self.average_kps > 5:
            self.last_activity = self.activity
            self.activity = 2
        print(f"current activity level: {self.activity}")
        print(f"last activity level: {self.last_activity}")
    
    def set_current_chunk(self, current_duration):
        current_duration = current_duration / 1000
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
        print(f"current chunk: {self.current_chunk}")
        print(f"current subchunk: {self.current_subchunk}")
    
    def check_activity(self):
        if self.last_keypress + 1 < time():
            self.kps = self.current_key_presses
            self.current_key_presses = 0
            self.calculate_average_kps()
            self.last_keypress = time()
        
        if self.is_transitioning:
            return

        current_chunk = self.audio_chunks[self.current_chunk]
        current_subchunk = self.audio_chunks[self.current_chunk].subchunks[self.current_subchunk]
        for chunk in self.audio_chunks.values():
            if chunk.activity_needed == self.activity:
                current_activity_chunk = chunk
        
        if self.activity == 0 and self.last_activity == 1 or self.activity == 0 and self.last_activity == 2:
            self.last_activity = self.activity
            self.transition(current_subchunk, self.primary_player.position(), self.audio_chunks["low activity 1"])
        elif self.activity == 1 and self.last_activity == 0:
            self.last_activity = self.activity
            self.transition(current_subchunk, self.primary_player.position(), self.audio_chunks["medium activity 1"])
        elif self.activity == 1 and self.last_activity == 2:
            self.last_activity = self.activity
            self.transition(current_subchunk, self.primary_player.position(), self.audio_chunks["medium activity 1"].subchunks["chunk 2"])
        elif self.activity == 2 and self.last_activity == 1 or self.activity == 2 and self.last_activity == 0:
            self.last_activity = self.activity
            self.transition(current_subchunk, self.primary_player.position(), self.audio_chunks["high activity 1"])
        #? test to see if a smooth loop transition sounds good
        elif self.activity == self.last_activity and self.primary_player.position() / 1000 == current_chunk.end_time - 1 or self.primary_player.position() > current_activity_chunk.end_time * 1000:
            loop_start_chunk = [chunk for chunk in current_activity_chunk.subchunks.values() if chunk.loop_start == True][0]
            self.transition(current_subchunk, self.primary_player.position(), loop_start_chunk)
            
    def loop_chunk(self, current_duration, chunk):
        if current_duration == chunk.end_time :
            self.primary_player.setPosition(chunk.start_time)
        
    def transition(self, start_chunk, current_duration, end_chunk):
        current_duration = current_duration / 1000
        print("transition time")
        print(f"start chunk: {start_chunk}")
        print(f"current position: {current_duration}")
        print(f"end chunk: {end_chunk}")
        self.is_transitioning = True
        
        def not_transition():
            self.is_transitioning = False
        self.transition_timeout.timeout.connect(not_transition)
        
        self.primary_player.pause_fade_out()
        self.secondary_player.setPosition(int(end_chunk.start_time * 1000))
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
key_press_thread.signals.result.connect(test.calculate_kps)
thread_manager.threadpool.start(key_press_thread)


# main_window = MainWindow()
# app.setApplicationName(title)
# main_window.setWindowTitle(title)
# main_window.setup_widgets()
# main_window.show()
    
sys.exit(app.exec())
