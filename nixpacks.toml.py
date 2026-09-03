# Le dice a Railway (Nixpacks) que instale ffmpeg a nivel de sistema,
# necesario para que el bot pueda reproducir música (music.py).
#
# El "..." es obligatorio: le dice a Nixpacks que AGREGUE ffmpeg a lo que ya
# detecta automáticamente (Python + sus dependencias), en vez de reemplazarlo.
[phases.setup]
nixPkgs = ["...", "ffmpeg"]
