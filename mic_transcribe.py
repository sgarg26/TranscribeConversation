import asyncio

# This example uses the sounddevice library to get an audio stream from the
# microphone. It's not a dependency of the project but can be installed with
# `pip install sounddevice`.
import sounddevice


from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

from anthropic import AnthropicBedrock


"""
Here's an example of a custom event handler you can extend to
process the returned transcription results as needed. This
handler will simply print the text out to your interpreter.
"""

client = AnthropicBedrock()

async def get_message(msg):
    s = ""
    with client.messages.stream(
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": f"Assume you're a developer. Identify if there's a valid question in the message in quotes. \
                If there's no question, just answer 'no', and if there is, remember to answer it concisely: '{msg}'"
            }
        ],
        model="anthropic.claude-3-sonnet-20240229-v1:0",
    ) as stream:
        for text in stream.text_stream:
            # print(text, "printed here", end="", flush=True)
            s += text
        # print()
    return s

class StoreTranscript(TranscriptResultStreamHandler):
    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        results = transcript_event.transcript.results
        for result in results:
            if not result.is_partial:
                s = result.alternatives[-1].transcript
                print(s)
                # self.transcript += s + "\n"


class MyEventHandler(TranscriptResultStreamHandler):

    async def handle_transcript_event(self, transcript_event: TranscriptEvent):
        # This handler can be implemented to handle transcriptions as needed.
        # Here's an example to get started.
        results = transcript_event.transcript.results
        for result in results:
            if not result.is_partial:
                s = result.alternatives[-1].transcript
                ans = await get_message(s)
                if not ans == "No":
                    print(f"{s}: {ans}")
            # for alt in result.alternatives:
            #     print(alt.transcript)



async def mic_stream():
    # This function wraps the raw input stream from the microphone forwarding
    # the blocks to an asyncio.Queue.
    loop = asyncio.get_event_loop()
    input_queue = asyncio.Queue()

    def callback(indata, frame_count, time_info, status):
        loop.call_soon_threadsafe(input_queue.put_nowait, (bytes(indata), status))

    # Be sure to use the correct parameters for the audio stream that matches
    # the audio formats described for the source language you'll be using:
    # https://docs.aws.amazon.com/transcribe/latest/dg/streaming.html
    stream = sounddevice.RawInputStream(
        channels=1,
        samplerate=16000,
        callback=callback,
        blocksize=2048 * 2,
        dtype="int16",
    )
    # Initiate the audio stream and asynchronously yield the audio chunks
    # as they become available.
    with stream:
        while True:
            indata, status = await input_queue.get()
            yield indata, status


async def write_chunks(stream):
    # This connects the raw audio chunks generator coming from the microphone
    # and passes them along to the transcription stream.
    async for chunk, status in mic_stream():
        await stream.input_stream.send_audio_event(audio_chunk=chunk)
    await stream.input_stream.end_stream()


async def basic_transcribe():
    # Setup up our client with our chosen AWS region
    transcript = ""
    client = TranscribeStreamingClient(region="us-east-1")

    # Start transcription to generate our async stream
    stream = await client.start_stream_transcription(
        language_code="en-US",
        media_sample_rate_hz=16000,
        media_encoding="pcm",
        show_speaker_label=True
    )

    # Instantiate our handler and start processing events
    # handler = MyEventHandler(stream.output_stream)
    handler = StoreTranscript(stream.output_stream)

    await asyncio.gather(write_chunks(stream), handler.handle_events())


loop = asyncio.get_event_loop()
loop.run_until_complete(basic_transcribe())
loop.close()