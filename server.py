from aiohttp import web
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


async def handle_map(request):
    file_path = os.path.join(BASE_DIR, "webapp", "index.html")
    return web.FileResponse(file_path)


async def handle_static(request):
    filename = request.match_info["filename"]
    file_path = os.path.join(BASE_DIR, "webapp", filename)
    return web.FileResponse(file_path)


def app():
    app = web.Application()
    app.router.add_get("/map/", handle_map)
    app.router.add_get("/map/{filename}", handle_static)
    return app


# Для локального запуска
if __name__ == "__main__":
    web.run_app(app(), host="0.0.0.0", port=8080)
