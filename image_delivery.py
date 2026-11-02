"""Bounded, disk-cached display copies of public PAC photographs."""
import hashlib
import os
import threading
from pathlib import Path
from urllib.parse import urlsplit, unquote
from flask import abort, request, send_file

_lock = threading.Lock()
WIDTHS = (400, 800, 1600)

def register(app, data, fleet_dir, fleet):
    @app.get('/media/image')
    def public_image():
        raw = request.args.get('src', '')
        url = urlsplit(raw)
        if url.scheme or url.netloc or url.fragment:
            abort(400)
        path = unquote(url.path)
        if path.startswith('/api/fleet/') and path.endswith('/photo'):
            code = path[len('/api/fleet/'):-len('/photo')]
            if code not in fleet: abort(404)
            source = next((p for p in fleet_dir.glob(code+'.*') if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')), Path(app.static_folder)/'fleet'/ (code+'.jpg'))
            base = fleet_dir if source.parent == fleet_dir else Path(app.static_folder)/'fleet'
        elif path.startswith('/gallery/'):
            base = data/'gallery'; source = base/path[len('/gallery/'):]
        elif path.startswith('/static/fleet/'):
            base = Path(app.static_folder)/'fleet'; source = base/path[len('/static/fleet/'):]
        else:
            abort(400)
        base = base.resolve(); source = source.resolve()
        if not source.is_relative_to(base) or source.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or not source.is_file(): abort(404)
        try: width = int(request.args.get('w', '800'))
        except ValueError: abort(400)
        if width not in WIDTHS: abort(400)
        st = source.stat()
        # One file per source and supported width. Replacements overwrite, not accumulate.
        key = hashlib.sha256((str(source)+':'+str(width)).encode()).hexdigest()
        version = hashlib.sha256(f'{st.st_mtime_ns}:{st.st_size}:v1'.encode()).hexdigest()
        cache = data/'image-cache'; output = cache/(key+'.webp'); marker = cache/(key+'.version')
        try:
            from PIL import Image, ImageOps
            with _lock:
                if not output.is_file() or not marker.is_file() or marker.read_text() != version:
                    cache.mkdir(exist_ok=True)
                    with Image.open(source) as im:
                        if im.width * im.height > 40_000_000: raise ValueError('Image too large')
                        im = ImageOps.exif_transpose(im)
                        im.thumbnail((width, width), Image.Resampling.LANCZOS)
                        im = im.convert('RGBA' if 'A' in im.getbands() else 'RGB')
                        temp = output.with_suffix('.tmp')
                        try:
                            im.save(temp, format='WEBP', quality=82, method=4)
                            os.replace(temp, output)
                            marker.write_text(version)
                        finally: temp.unlink(missing_ok=True)
            response = send_file(output, mimetype='image/webp', conditional=True, etag=key+version, max_age=86400)
        except (ImportError, OSError, ValueError, Image.DecompressionBombError if 'Image' in locals() else ValueError):
            # The original remains available if Pillow or a cache write is unavailable.
            response = send_file(source, conditional=True, max_age=0)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
