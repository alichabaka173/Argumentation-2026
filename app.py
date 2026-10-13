import os
from flask import Flask, request, render_template_string, Response
from aba import generate, ABAError

app = Flask(__name__)
EXAMPLE = open(os.path.join(os.path.dirname(__file__), "exemple.txt"), encoding="utf-8").read()

PAGE = """<!doctype html><meta charset="utf-8"><title>ABA Generator</title>
<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}
textarea{width:100%;height:320px;font-family:monospace}pre{background:#f4f4f4;padding:1rem;overflow:auto}
.err{color:#b00020}</style>
<h1>ABA Generator</h1>
<form method="post" action="/">
<textarea name="text">{{ text }}</textarea><br>
<button type="submit">Générer</button>
</form>
{% if error %}<p class="err">Erreur : {{ error }}</p>{% endif %}
{% if result %}<pre>{{ result }}</pre>{% endif %}"""

@app.route("/", methods=["GET", "POST"])
def index():
    text = request.form.get("text", EXAMPLE)
    result = error = None
    if request.method == "POST":
        try:
            result = generate(text)[0]
        except ABAError as e:
            error = str(e)
    return render_template_string(PAGE, text=text, result=result, error=error)

@app.route("/api/generate", methods=["POST"])
def api():
    """curl -X POST --data-binary @exemple.txt https://<url>/api/generate"""
    try:
        return Response(generate(request.get_data(as_text=True))[0], mimetype="text/plain")
    except ABAError as e:
        return Response(f"Erreur : {e}", status=400, mimetype="text/plain")

@app.route("/health")
def health():
    return "ok"
