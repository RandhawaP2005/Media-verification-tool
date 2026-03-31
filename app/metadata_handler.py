from datetime import datetime
import io
import json
import uuid
import c2pa
import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from sqlalchemy import exc

with open("cert.pem", "rb") as cert_file:
    certs = cert_file.read()
with open("signing.key", "rb") as key_file:
    key = key_file.read()
TSA_URL = os.getenv("C2PA_TSA_URL")

def create_manifest(format:str, title:str, existing:bool):
    now = datetime.now()
    
    if existing:
        #TODO: implement logic to extract existing xmp instance id. For now, generating new on upload
        instance_id = f"xmp:iid:{uuid.uuid4()}"
        manifest_definition = {
            "claim_generator": "MediaAuthenticityVerifier/0.1",
            "claim_generator_info": [{
                "name" : "MediaAuthenticityVerifier/0.1",
                "version" : "0.1"
            }],
            "format" : format,
            "ingredients" : [{
                "title": title,
                "format": format,
                "relationship" : "parentOf",
                "instance_id": instance_id
            }],
            "assertions" : [{
                "label" : "c2pa.actions",
                "data": {
                    "actions": [{
                        "action" : "c2pa.opened",
                        "parameters" : {
                            "ingredientIds": instance_id
                        },
                        "when": str(now.date()) + "T" + str(now.strftime("%H:%M:%S"))+ "Z",
                        "softwareAgent": {
                            "name": "Media-Verification-Tool",
                            "version": "0.1"
                        },
                        #TODO: Implement logic to check if the media came from a trusted source and also implement origin
                        "digitalSourceType": ""
                    }]
                }
            }]
        }
    else:
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
                        "when": now.date + "T" + now.strftime("%H:%M:%S")+ "Z",
                        "softwareAgent": {
                            "name": "Media-Verification-Tool",
                            "version": "0.1"
                        },
                        #TODO: Implement logic to check if the media came from a trusted source or algorithmically generated and also implement origin
                        "digitalSourceType": "https://cv.iptc.org/newscodes/digitalsourcetype/digitalCapture"
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

def sign_img(input, format: str, f_name:str, existing:bool) -> bytes:
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
        with c2pa.Builder(create_manifest(format, f_name, existing)) as builder:
            builder.sign(
                signer,format,input,output
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


def verify_img(input, format:str):
    try:
        if isinstance(input, (bytes, bytearray)):
            input = io.BytesIO(bytes(input))
        if hasattr(input, "seek"):
            input.seek(0)
        
        settings_dict = {
        "verify": {
            "verify_cert_anchors": True
            }
        }

        settings = c2pa.Settings.from_dict(settings_dict)
        with c2pa.Context(settings) as ctx:
            with c2pa.Reader(format, input) as reader:
                manifest_store = reader.json()

                return {
                    "manifest_store" : manifest_store,
                    "active_manifest" : reader.get_active_manifest,
                    "validation_state" : reader.get_validation_state,
                    "validation_results" : reader.get_validation_results
                }

    except Exception as err:
        print(err)
