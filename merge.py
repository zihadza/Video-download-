import os, re, subprocess, time

FOLDER = "/storage/emulated/0/Zihad/Video-download-"
MERGED_FOLDER = os.path.join(FOLDER, "merged")

if not os.path.exists(MERGED_FOLDER):
    os.makedirs(MERGED_FOLDER)

def clean_name(name):
    """
    Remove .f123456789v/.f123456789a suffix and temp extensions
    """
    name = re.sub(r'\.f\d+[av]$', '', name)  # Remove .f1234567v/.f1234567a
    name = re.sub(r'\.temp$', '', name)       # Remove .temp
    return name.strip()

def scan_files():
    files = os.listdir(FOLDER)
    videos = {}
    audios = {}

    for f in files:
        if f.endswith(".temp.webm"):  # skip temp download files
            continue
        path = os.path.join(FOLDER, f)
        if not os.path.isfile(path):
            continue
        name, ext = os.path.splitext(f)
        ext = ext.lower()
        base_name = clean_name(name)

        if ext in [".mp4", ".webm", ".mkv"]:
            videos[base_name] = f
        elif ext in [".m4a", ".mp3", ".webm"]:
            audios[base_name] = f

    # Only pair audio+video which both exist
    mergeable = []
    for b in videos:
        if b in audios:
            mergeable.append((videos[b], audios[b]))
    return mergeable

def merge_files(video_file, audio_file):
    video_path = os.path.join(FOLDER, video_file)
    audio_path = os.path.join(FOLDER, audio_file)
    base_name = clean_name(os.path.splitext(video_file)[0])
    output_file = os.path.join(MERGED_FOLDER, f"{base_name}_merged.webm")

    print(f"Merging:\n Video: {video_file}\n Audio: {audio_file}\n -> Output: {output_file}")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-i", audio_path,
        "-c", "copy",
        "-y",
        output_file
    ]
    try:
        subprocess.run(cmd, check=True)
        print("Merge completed ✅")
        # Delete originals after merge
        os.remove(video_path)
        os.remove(audio_path)
        print("Original files deleted 🗑️\n")
    except subprocess.CalledProcessError as e:
        print("Merge failed ❌", e)

def main():
    print(f"Scanning folder: {FOLDER}")
    print(f"Merged output folder: {MERGED_FOLDER}\n")

    while True:
        merge_list = scan_files()
        if not merge_list:
            time.sleep(10)
            continue
        for video, audio in merge_list:
            merge_files(video, audio)
        time.sleep(5)

if __name__ == "__main__":
    main()
