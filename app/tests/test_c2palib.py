import c2pa
import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend

output_dir = os.path.join(os.path.dirname(__file__), "/img/outputs/")
input_dir = os.path.join(os.path.dirname(__file__), "/img/inputs/")

with open("cert.pem", "rb") as cert_file:
    certs = cert_file.read()
with open("signing.key", "rb") as key_file:
    key = key_file.read()


# For now lets not think about ingredients (combining images with existing manifests to derive a new image)
# Possibly add a thumbnail assertion
manifest_definition = {
    "claim_generator": "python_test",      # info of the user in our context. Also potentially add user OS and user icon(pfp)
    "claim_generator_info": [{
        "name" : "python_test",
        "version": "0.0.1"
    }],
    "format": "image/jpeg",
    "ingredients": [],
    "assertions": [
        {
            "label" : "c2pa.actions",
            "data": {
                "actions" : [
                    {
                        "action": "c2pa.open",
                        "actor" : "dummy_device",
                        "softwareagent": "Media-Verification-Tool/0.1"
                    }
                ]
            }
        }
    ]
}

def callback_signer_es256(data:bytes) -> bytes:
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

with c2pa.Signer.from_callback(
        callback=callback_signer_es256,
        alg=c2pa.C2paSigningAlg.ES256,
        certs = certs.decode('utf-8'),
        tsa_url="http://timestamp.digicert.com" 
)as signer:
   
        with c2pa.Builder(manifest_definition) as builder:
            file = builder.sign_file(
                source_path="img/inputs/image.jpg",
                dest_path="img/outputs/image_signed.jpg",
                signer=signer
            )



        