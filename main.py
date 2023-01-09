import streamlit as st
import requests
import json
from pathlib import Path
import ffmpeg
from difflib import Differ
import time

API_KEY = str(st.secrets["SIEVE_API_KEY"])

st.title("text2cut")
st.markdown('Built by [Gaurang Bharti](https://twitter.com/gaurang_bharti) using [Sieve](https://www.sievedata.com)')

def check_status(url, interval, job_id):
    finished = False
    headers = {
        'X-API-Key': API_KEY
        }
    while True:
        response = requests.get(url, headers=headers)
        print(response.json())
        data = response.json()['data']
        #print(data)
        for job in data:
            if job['job_id'] == job_id:
                print(job_id)
                if job['status'] == 'processing':
                    print("processing")
                    time.sleep(interval)
                if job['status'] == 'finished':
                    print("finished")
                    finished = True
                    return finished
                if job['status'] == 'failed':
                    return job['error']

def fetch_transcript(job_id):
    print(job_id)
    url = 'https://v1-api.sievedata.com/v1/query/metadata'
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    }
    data = {
        "job_id": job_id,
        "project_name": "text2cut_object"
        }
    response = requests.post(url, headers = headers, json=data)
    data = response.json()
    print(len(data))
    transcript = data['data'][0]['transcription']
    timestamps = data['data'][0]['timestamps']
    
    return (transcript, transcript, timestamps)
        
def get_jobs():
    url = "https://v1-api.sievedata.com/v1/projects/text2cut_object/jobs"
    headers = {
        'X-API-Key': API_KEY
        }
    response = requests.get(url, headers=headers)
    return len(response.json()['data'])+1

@st.experimental_memo(suppress_st_warning=True, persist="disk")
def send_data(video_link):
    url = "https://v1-api.sievedata.com/v1/push"
    
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    } 
    
    data = {
        "project_name": "text2cut_object",
        "source_name": str("input" + str(get_jobs())),
        "source_url": str(video_link),
        "user_metadata": {
            "video_link": str(video_link),
        }
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        if ('job_id') not in response.json():
            st.error(response.json()['description'])
            return False
        print("Success")
        return (response.json()['job_id'])
    except Exception as e:
        return (f'An error occurred: {e}')

def cut_timestamps_to_video(video_in, transcription, text_in, timestamps):
    video_path = Path(video_in)
    video_file_name = video_path.stem
    if(video_in == None or text_in == None or transcription == None):
        raise ValueError("Inputs undefined")

    d = Differ()
    # Compare original with edited transcript
    diff_chars = d.compare(transcription, text_in)
    # Remove text additions
    filtered = list(filter(lambda x: x[0] != '+', diff_chars))

    # Group character timestamps
    idx = 0
    grouped = {}
    for (a, b) in zip(filtered, timestamps):
        if a[0] != '-':
            if idx in grouped:
                grouped[idx].append(b)
            else:
                grouped[idx] = []
                grouped[idx].append(b)
        else:
            idx += 1

    timestamps_to_cut = [[v[0][1], v[-1][2]] for v in grouped.values()]

    between_str = '+'.join(
        map(lambda t: f'between(t,{t[0]},{t[1]})', timestamps_to_cut))

    if timestamps_to_cut:
        video_file = ffmpeg.input(video_in)
        video = video_file.video.filter(
            "select", f'({between_str})').filter("setpts", "N/FRAME_RATE/TB")
        audio = video_file.audio.filter(
            "aselect", f'({between_str})').filter("asetpts", "N/SR/TB")

        output_video = f'./videos_out/{video_file_name}.mp4'
        ffmpeg.concat(video, audio,  v=1, a=1).output(
            output_video).overwrite_output().global_args('-loglevel', 'quiet').run()

    else:
        output_video = video_in

    tokens = [(token[2:], token[0] if token[0] != " " else None)
              for token in filtered]
    return (tokens, output_video)

#Streamlit App

video_in = st.text_input("Enter Video URL")
button1 = st.button("Transcribe")

if st.session_state.get('button') != True:

    st.session_state['button'] = button1

if st.session_state['button'] == True:
    
    job = send_data(video_in)
    if job:
        with st.spinner("Processing video"):
            status = check_status('https://v1-api.sievedata.com/v1/projects/text2cut_object/jobs', 5, str(job))
            if status == True:
                text_in, transcription_var, timestamps_var = fetch_transcript(job)
    
    text_in = st.text_area("Drag down from the bottom right corner to make the text box bigger", transcription_var)
    if st.button('Cut Video'):
        tokens, cut_video = cut_timestamps_to_video(video_in, transcription_var, text_in, timestamps_var)
        st.video(cut_video)
        st.session_state['button'] = False