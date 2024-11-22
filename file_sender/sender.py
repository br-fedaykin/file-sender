from pathlib import Path
from typing import List
from typing_extensions import Annotated
import typer
import logging
import socket
import boto3  # type: ignore
from botocore.exceptions import BotoCoreError, NoCredentialsError  # type: ignore
import zipfile
from typer_config import use_yaml_config
from email.message import EmailMessage
from typer_config.callbacks import argument_list_callback

app = typer.Typer(add_completion=False, help="Envia arquivos por e-mail")

hostname = socket.gethostname()
DEFAULT_MSG = f"Mensagem enviada via script do host {hostname} usando AWS SES."
LOG_FILE = "sender.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(module)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),  # Log também no terminal
    ],
)
logger = logging.getLogger(__name__)


def __build_message(
    sender_email: str, recipient_email: List[str], subject: str, msg: str
):
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = sender_email
    email["To"] = ", ".join(recipient_email)
    email.set_content(msg)
    return email


def __compress_file(file: Path):
    logger.info(f"Compressing the file {file}")
    zip_file = file.with_suffix(".zip")
    with zipfile.ZipFile(zip_file, "w") as z:
        z.write(
            file, arcname=file.name, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
        )
    return zip_file


@app.command()
@use_yaml_config()
def send_aws_ses(
    attachment: Path,
    sender_email: str,
    recipient_email: List[str] = typer.Argument(
        default=None, callback=argument_list_callback
    ),
    subject: str = "AWS SES Email",
    msg: str = DEFAULT_MSG,
    compress: Annotated[
        bool, typer.Option("--compress", help="comprime o anexo do arquivo")
    ] = False,
):
    """
    Envia um arquivo por email usando AWS SES.
    """
    if compress:
        attachment = __compress_file(attachment)
    email = __build_message(sender_email, recipient_email, subject, msg)

    logger.info(f"Preparing to send file: {attachment}")
    with open(attachment, "rb") as f:
        email.add_attachment(
            f.read(),
            maintype="application",
            subtype="octet-stream",
            filename=attachment.name,
        )

    try:
        client = boto3.client("ses", region_name="us-east-1")
        response = client.send_raw_email(
            Source=sender_email,
            Destinations=recipient_email,
            RawMessage={"Data": email.as_bytes()},
        )
        logger.info(
            f"Email sent successfully to {recipient_email}. Message ID: {response['MessageId']}"
        )
    except (BotoCoreError, NoCredentialsError) as e:
        logger.error(f"Failed to send email: {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()