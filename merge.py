import os, re, subprocess, time

FOLDER = "/storage/emulated/0/Zihad/Video-download-"
MERGED_FOLDER = os.path.join(FOLDER, "merged")

if not os.path.exists(MERGED_FOLDER):
    os.makedirs(MERGED_FOLDER)

def scan_files():
    files = os.listdir(FOLDER)
    videos = {}
    audios = {}
    for f in files:
        if f.endswith(".temp.webm"):  
            continue
        name, ext = os.path.splitext(f)
        base_name = re.sub(r'\.f\d+[av]$', '', name)
        ext = ext.lower()
        if ext in [".mp4", ".webm", ".mkv"]:
            videos[base_name] = f
        if ext in [".m4a", ".mp3", ".webm"]:
            audios[base_name] = f
    mergeable = []
    for n in videos:
        if n in audios:
            mergeable.append((videos[n], audios[n]))
    return mergeable

def merge_files(video_file, audio_file):
    base_name = re.sub(r'\.f\d+[av]$', '', os.path.splitext(video_file)[0])
    output_file = os.path.join(MERGED_FOLDER, f"{base_name}_merged.webm")
    video_path = os.path.join(FOLDER, video_file)
    audio_path = os.path.join(FOLDER, audio_file)

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
        os.remove(video_path)
        os.remove(audio_path)
        print("Original files deleted 🗑️\n")
    except subprocess.CalledProcessError as e:
        print("Merge failed ❌", e)

def main():
    while True:
        merge_list = scan_files()
        if not merge_list:
            print("No mergeable files found! Waiting 10s...")
            time.sleep(10)
            continue
        for video, audio in merge_list:
            merge_files(video, audio)
        time.sleep(5)

if __name__ == "__main__":
    print(f"Scanning folder: {FOLDER}")
    print(f"Merged output folder: {MERGED_FOLDER}\n")
    main()
