from reachy_mini import ReachyMini

with ReachyMini(media_backend="default") as mini:
    mini.media.start_playing()
    mini.media.play_sound("C:/Windows/Music/fart.mp3") # change path to your own mp3 file
    import time; time.sleep(2)
    mini.media.stop_playing()