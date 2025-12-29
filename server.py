@app.route("/mp3")
def mp3():
    if not check_key(request):
        return jsonify({"error": "Invalid API Key"}), 401

    url = request.args.get("url")
    quality = request.args.get("quality", "192")

    if quality not in ["128", "192", "320"]:
        quality = "192"

    temp_dir = tempfile.mkdtemp()

    opts = ydl_opts_base()
    opts.update({
        "format": "bestaudio/best",
        "outtmpl": os.path.join(temp_dir, "%(title).40s.%(id)s.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality,
        }],
    })

    if FFMPEG_PATH:
        opts["ffmpeg_location"] = FFMPEG_PATH

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # ✅ playlist safety
        if info.get("_type") == "playlist":
            info = info["entries"][0]

        # ✅ find mp3 safely
        mp3_file = None
        for f in os.listdir(temp_dir):
            if f.endswith(".mp3"):
                mp3_file = os.path.join(temp_dir, f)
                break

        if not mp3_file:
            return jsonify({"error": "MP3 not generated"}), 500

        return send_file(
            mp3_file,
            as_attachment=True,
            download_name=os.path.basename(mp3_file)
        )

    except Exception as e:
        logger.error("MP3 ERROR", exc_info=True)
        return jsonify({
            "error": "mp3_failed",
            "detail": str(e)
        }), 500
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
./ffmpeg -version
app.run(host="0.0.0.0", port=8080, debug=True)

