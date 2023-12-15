from gtts import gTTS
import edge_tts, asyncio, nest_asyncio
from tqdm import tqdm
import librosa, os, re, torch, gc, subprocess
from .language_configuration import fix_code_language, bark_voices_list, vits_voices_list
import numpy as np
#from scipy.io.wavfile import write as write_wav
import soundfile as sf

device = "cuda:0" if torch.cuda.is_available() else "cpu"
torch_dtype_env = torch.float16 if torch.cuda.is_available() else torch.float32

class TTS_OperationError(Exception):
    def __init__(self, message="The operation did not complete successfully."):
        self.message = message
        super().__init__(self.message)


def edge_tts_voices_list():
    completed_process = subprocess.run(
        ["edge-tts", "--list-voices"], capture_output=True, text=True
    )
    lines = completed_process.stdout.strip().split("\n")

    voices = []
    for line in lines:
        if line.startswith("Name: "):
            voice_entry = {}
            voice_entry["Name"] = line.split(": ")[1]
        elif line.startswith("Gender: "):
            voice_entry["Gender"] = line.split(": ")[1]
            voices.append(voice_entry)

    formatted_voices = [f"{entry['Name']}-{entry['Gender']}" for entry in voices]

    if not formatted_voices:
        print("The list of Edge TTS voices could not be obtained, switching to an alternative method")
        tts_voice_list = asyncio.new_event_loop().run_until_complete(edge_tts.list_voices())
        formatted_voices = sorted([f"{v['ShortName']}-{v['Gender']}" for v in tts_voice_list])

    if not formatted_voices:
        print("Can't get EDGE TTS - list voices")

    return formatted_voices

def edge_request_tts(tts_text, tts_voice, filename, language, is_gui=False):
    print(tts_text, filename)
    try:
        #nest_asyncio.apply() if not is_gui else None
        asyncio.run(edge_tts.Communicate(tts_text, "-".join(tts_voice.split('-')[:-1])).save(filename))
    except Exception as error:
      print(str(error))
      try:
        tts = gTTS(tts_text, lang=fix_code_language(language))
        tts.save(filename)
        print(f'No audio was received. Please change the tts voice for {tts_voice}. TTS auxiliary will be used in the segment')
      except:
        tts = gTTS('a', lang=fix_code_language(language))
        tts.save(filename)
        print('Error: Audio will be replaced.')

def segments_egde_tts(filtered_edge_segments, TRANSLATE_AUDIO_TO, is_gui):

    for segment in tqdm(filtered_edge_segments['segments']):

        speaker = segment['speaker']
        text = segment['text']
        start = segment['start']
        tts_name = segment['tts_name']

        # make the tts audio
        filename = f"audio/{start}.ogg"
        edge_request_tts(text, tts_name, filename, TRANSLATE_AUDIO_TO, is_gui)


def segments_bark_tts(filtered_bark_segments, TRANSLATE_AUDIO_TO, model_id_bark="suno/bark-small"):
    from transformers import AutoProcessor, AutoModel, BarkModel
    from optimum.bettertransformer import BetterTransformer

    # load model bark
    model = BarkModel.from_pretrained(model_id_bark, torch_dtype=torch_dtype_env).to(device)
    model = model.to(device)
    processor = AutoProcessor.from_pretrained(model_id_bark, return_tensors="pt") # , padding=True
    if torch.cuda.is_available():
        # convert to bettertransformer
        model = BetterTransformer.transform(model, keep_original_model=False)
        # enable CPU offload
        #model.enable_cpu_offload()
    sampling_rate = model.generation_config.sample_rate

    #filtered_segments = filtered_bark_segments['segments']
    # Sorting the segments by 'tts_name'
    #sorted_segments = sorted(filtered_segments, key=lambda x: x['tts_name'])
    #print(sorted_segments)

    for segment in tqdm(filtered_bark_segments['segments']):

        speaker = segment['speaker']
        text = segment['text']
        start = segment['start']
        tts_name = segment['tts_name']

        inputs = processor(text, voice_preset=bark_voices_list[tts_name]).to(device)

        # make the tts audio
        filename = f"audio/{start}.ogg"
        print(text, filename)
        try:
            # Infer
            with torch.inference_mode():
                speech_output = model.generate(**inputs, do_sample = True, fine_temperature = 0.4, coarse_temperature = 0.8, pad_token_id=processor.tokenizer.pad_token_id)
            # Save file
            sf.write(
                file=filename,
                samplerate=sampling_rate,
                data=speech_output.cpu().numpy().squeeze().astype(np.float32),
                format='ogg', subtype='vorbis'
            )
        except Exception as error:
            print(f"Error: {str(error)}")
            try:
              tts = gTTS(text, lang=fix_code_language(TRANSLATE_AUDIO_TO))
              tts.save(filename)
              print(f'For {tts_name} the TTS auxiliary will be used')
            except Exception as error:
              print(f"Error: {str(error)}")
              sample_rate_aux = 22050
              duration = float(segment['end']) - float(segment['start'])
              data = np.zeros(int(sample_rate_aux * duration)).astype(np.float32)
              sf.write(filename, data, sample_rate_aux, format='ogg', subtype='vorbis')
              print('Error: Audio will be replaced -> [silent audio].')
        gc.collect(); torch.cuda.empty_cache()
    del processor; del model; gc.collect(); torch.cuda.empty_cache()


def uromanize(input_string):
    """Convert non-Roman strings to Roman using the `uroman` perl package."""
    #script_path = os.path.join(uroman_path, "bin", "uroman.pl")

    if not os.path.exists("./uroman"):
        print("Clonning repository uroman https://github.com/isi-nlp/uroman.git for romanize the text")
        process = subprocess.Popen(["git", "clone", "https://github.com/isi-nlp/uroman.git"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
    script_path = os.path.join("./uroman", "bin", "uroman.pl")

    command = ["perl", script_path]

    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Execute the perl command
    stdout, stderr = process.communicate(input=input_string.encode())

    if process.returncode != 0:
        raise ValueError(f"Error {process.returncode}: {stderr.decode()}")

    # Return the output as a string and skip the new-line character at the end
    return stdout.decode()[:-1]

def segments_vits_tts(filtered_vits_segments, TRANSLATE_AUDIO_TO):
    from transformers import VitsModel, AutoTokenizer

    filtered_segments = filtered_vits_segments['segments']
    # Sorting the segments by 'tts_name'
    sorted_segments = sorted(filtered_segments, key=lambda x: x['tts_name'])
    print(sorted_segments)

    model_name_key = None
    for segment in tqdm(sorted_segments):

        speaker = segment['speaker']
        text = segment['text']
        start = segment['start']
        tts_name = segment['tts_name']

        if tts_name != model_name_key:
            model_name_key = tts_name
            model = VitsModel.from_pretrained(vits_voices_list[tts_name])
            tokenizer = AutoTokenizer.from_pretrained(vits_voices_list[tts_name])
            sampling_rate = model.config.sampling_rate

        if tokenizer.is_uroman:
            romanize_text = uromanize(text)
            print(f"Romanize text: {romanize_text}")
            inputs = tokenizer(romanize_text, return_tensors="pt")
        else:
            inputs = tokenizer(text, return_tensors="pt")

        # make the tts audio
        filename = f"audio/{start}.ogg"
        print(text, filename)
        try:
            # Infer
            with torch.no_grad():
              speech_output = model(**inputs).waveform
            # Save file
            sf.write(
                file=filename,
                samplerate=sampling_rate,
                data=speech_output.cpu().numpy().squeeze().astype(np.float32),
                format='ogg', subtype='vorbis'
            )
        except Exception as error:
            print(f"Error: {str(error)}")
            try:
              tts = gTTS(text, lang=fix_code_language(TRANSLATE_AUDIO_TO))
              tts.save(filename)
              print(f'For {tts_name} the TTS auxiliary will be used')
            except Exception as error:
              print(f"Error: {str(error)}")
              sample_rate_aux = 22050
              duration = float(segment['end']) - float(segment['start'])
              data = np.zeros(int(sample_rate_aux * duration)).astype(np.float32)
              sf.write(filename, data, sample_rate_aux, format='ogg', subtype='vorbis')
              print('Error: Audio will be replaced -> [silent audio].')
        gc.collect(); torch.cuda.empty_cache()
    try:
        del tokenizer; del model; gc.collect(); torch.cuda.empty_cache()
    except:
        pass


def audio_segmentation_to_voice(
    result_diarize, TRANSLATE_AUDIO_TO, max_accelerate_audio, is_gui,
    tts_voice00, tts_voice01, tts_voice02, tts_voice03, tts_voice04, tts_voice05,
    model_id_bark="suno/bark-small"
    ):

    # Mapping speakers to voice variables
    speaker_to_voice = {
        'SPEAKER_00': tts_voice00,
        'SPEAKER_01': tts_voice01,
        'SPEAKER_02': tts_voice02,
        'SPEAKER_03': tts_voice03,
        'SPEAKER_04': tts_voice04,
        'SPEAKER_05': tts_voice05
    }

    # Assign 'SPEAKER_00' to segments without a 'speaker' key
    for segment in result_diarize['segments']:
        if 'speaker' not in segment:
            segment['speaker'] = 'SPEAKER_00'
            print(f"NO SPEAKER DETECT IN SEGMENT: First TTS will be used in the segment time {segment['start'], segment['text']}")
         # Assign the TTS name
        segment['tts_name'] = speaker_to_voice[segment['speaker']]

    # Find TTS method
    pattern_edge = re.compile(r'.*-(Male|Female)$')
    pattern_bark = re.compile(r'.* BARK$')
    pattern_vits = re.compile(r'.* VITS$')

    speakers_edge = [speaker for speaker, voice in speaker_to_voice.items() if pattern_edge.match(voice)]
    speakers_bark = [speaker for speaker, voice in speaker_to_voice.items() if pattern_bark.match(voice)]
    speakers_vits = [speaker for speaker, voice in speaker_to_voice.items() if pattern_vits.match(voice)]

    # Filter method in segments
    filtered_edge = {"segments": [segment for segment in result_diarize['segments'] if segment['speaker'] in speakers_edge]}
    filtered_bark = {"segments": [segment for segment in result_diarize['segments'] if segment['speaker'] in speakers_bark]}
    filtered_vits = {"segments": [segment for segment in result_diarize['segments'] if segment['speaker'] in speakers_vits]}

    # Infer
    if filtered_edge["segments"]:
        print(f"EDGE TTS: {speakers_edge}")
        segments_egde_tts(filtered_edge, TRANSLATE_AUDIO_TO, is_gui) # mp3
    if filtered_bark["segments"]:
        print(f"BARK TTS: {speakers_bark}")
        segments_bark_tts(filtered_bark, TRANSLATE_AUDIO_TO, model_id_bark) # wav
    if filtered_vits["segments"]:
        print(f"VITS TTS: {speakers_vits}")
        segments_vits_tts(filtered_vits, TRANSLATE_AUDIO_TO) # wav

    [result.pop('tts_name', None) for result in result_diarize['segments']]
    return accelerate_segments(result_diarize, max_accelerate_audio, speakers_edge, speakers_bark, speakers_vits)


def accelerate_segments(result_diarize, max_accelerate_audio, speakers_edge, speakers_bark, speakers_vits):

    print("Apply acceleration")
    audio_files = []
    speakers_list = []
    for segment in tqdm(result_diarize['segments']):

        text = segment['text']
        start = segment['start']
        end = segment['end']
        speaker = segment['speaker']

        # find name audio
        #if speaker in speakers_edge:
        filename = f"audio/{start}.ogg"
        #elif speaker in speakers_bark + speakers_vits:
        #    filename = f"audio/{start}.wav" # wav

        # duration
        duration_true = end - start
        duration_tts = librosa.get_duration(filename=filename)

        # Accelerate percentage
        acc_percentage = duration_tts / duration_true

        if acc_percentage > max_accelerate_audio:
            acc_percentage = max_accelerate_audio
        elif acc_percentage <= 1.2 and acc_percentage >= 0.8:
            acc_percentage = 1.0
        elif acc_percentage <= 0.79:
            acc_percentage = 0.8

        # Smoth and round
        acc_percentage = round(acc_percentage+0.0, 1)

        # apply aceleration or opposite to the audio file in audio2 folder
        os.system(f"ffmpeg -y -loglevel panic -i {filename} -filter:a atempo={acc_percentage} audio2/{filename}")

        duration_create = librosa.get_duration(filename=f"audio2/{filename}")
        print(acc_percentage, duration_tts, duration_create)
        audio_files.append(filename)
        speakers_list.append(speaker)

    return audio_files, speakers_list

if __name__ == '__main__':
    from segments import result_diarize

    audio_segmentation_to_voice(
        result_diarize,
        TRANSLATE_AUDIO_TO="en",
        max_accelerate_audio=2.1,
        is_gui= True,
        tts_voice00='en-facebook-mms VITS',
        tts_voice01="en-CA-ClaraNeural-Female",
        tts_voice02="en-GB-ThomasNeural-Male",
        tts_voice03="en-GB-SoniaNeural-Female",
        tts_voice04="en-NZ-MitchellNeural-Male",
        tts_voice05="en-GB-MaisieNeural-Female",
        )