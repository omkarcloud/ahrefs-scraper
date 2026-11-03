"""Start the Ahrefs Scraper API.

    python run.py            # http://localhost:8000
    PORT=9000 python run.py  # another port

Then:  curl "http://localhost:8000/domains/overview?target=tesla.com"
"""
import bottle
from cheroot import wsgi

import config
import routes  # noqa: F401  (mounts the routes on bottle's default app)


def main():
    app = bottle.default_app()
    print(f"Ahrefs Scraper listening on http://localhost:{config.PORT}/")
    print(f"Try:  curl \"http://localhost:{config.PORT}/domains/overview?target=tesla.com\"")
    if not config.CAPSOLVER_API_KEY:
        print("Note: CAPSOLVER_API_KEY is not set, so only the overview, competitors and "
              "website ranking endpoints work (see config.py).")
    server = wsgi.Server(("0.0.0.0", config.PORT), app, server_name="ahrefs-scraper", numthreads=16)
    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
