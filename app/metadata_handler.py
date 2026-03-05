import io
import json
import c2pa
import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

with open("cert.pem", "rb") as cert_file:
    certs = cert_file.read()
with open("signing.key", "rb") as key_file:
    key = key_file.read()
TSA_URL = os.getenv("C2PA_TSA_URL")

def create_manifest(format:str):
    manifest_definition = {
        "claim_generator": "MediaAuthenticityVerifier/0.1",
        "claim_generator_info": [{
            "name" : "MediaAuthenticityVerifier/0.1",
            "version" : "0.1"
        }],
        "format" : format,
        "ingredients" : [],
        "assertions" : [{
            "label" : "c2pa.actions",
            "data": {
                "actions": [{
                    "action" : "c2pa.created",
                    "softwareAgent": {
                        "name": "Media-Verification-Tool",
                        "version": "0.1"
                    }
                }]
            }
        }]
    }

    return manifest_definition

def callback_signer_es256(data: bytes) -> bytes:
    """Callback function that signs data using ES256 algorithm."""
    private_key = serialization.load_pem_private_key(
        key,
        password=None,
        backend=default_backend()
    )
    signature = private_key.sign(
        data,
        ec.ECDSA(hashes.SHA256())
    )
    return signature

def sign_img(input, format: str) -> bytes:
    if isinstance(input, (bytes, bytearray)):
        input = io.BytesIO(bytes(input))
    if hasattr(input, "seek"):
        input.seek(0)
    output = io.BytesIO()

    signer_kwargs = {
        "callback": callback_signer_es256,
        "alg": c2pa.C2paSigningAlg.ES256,
        "certs": certs.decode("utf-8"),
    }
    if TSA_URL:
        signer_kwargs["tsa_url"] = TSA_URL

    with c2pa.Signer.from_callback(**signer_kwargs) as signer:
        with c2pa.Builder(create_manifest(format)) as builder:
            builder.sign(
                source=input,
                dest=output,
                signer=signer,
                format=format
            )
            output.seek(0)
            return output.read()


def get_manifest(input, format) -> json:
    try:
        if isinstance(input, (bytes, bytearray)):
            input = io.BytesIO(bytes(input))
        with c2pa.Reader(format, input) as reader:
            manifest = json.loads(reader.json())
            active_manifest = manifest["manifests"][manifest["active_manifest"]]
            if active_manifest:
                return active_manifest
            else:
                print("Error: No Manifest Attached to file.")

    except Exception as err:
        print(err)