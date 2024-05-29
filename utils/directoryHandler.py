from pathlib import Path
from config import DATABASE_BACKUP_TIME, STORAGE_CHANNEL, DATABASE_BACKUP_MSG_ID
from utils.clients import get_client
from pyrogram.types import InputMediaDocument
import pickle, os, random, string, asyncio
from utils.extra import get_current_utc_time
from utils.logger import Logger

logger = Logger("directoryHandler")
DRIVE_DATA = None
drive_cache_path = Path("./cache/drive.data")
drive_cache_path.parent.mkdir(parents=True, exist_ok=True)


def getRandomID():
    global DRIVE_DATA
    while True:
        id = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if id not in DRIVE_DATA.used_ids:
            DRIVE_DATA.used_ids.append(id)
            return id


class Folder:
    def __init__(self, name: str, path) -> None:
        self.name = name
        self.contents = {}
        if name == "/":
            self.id = "root"
        else:
            self.id = getRandomID()
        self.type = "folder"
        self.trash = False
        self.path = path[:-1] if path[-1] == "/" else path


class File:
    def __init__(
        self,
        name: str,
        file_id: int,
        size: int,
        path: str,
    ) -> None:
        self.name = name
        self.type = type
        self.file_id = file_id
        self.id = getRandomID()
        self.size = size
        self.type = "file"
        self.trash = False
        self.path = path[:-1] if path[-1] == "/" else path


class NewDriveData:
    def __init__(self, contents: dict, used_ids: list) -> None:
        self.contents = contents
        self.used_ids = used_ids
        self.isUpdated = False

    def save(self) -> None:
        with open(drive_cache_path, "wb") as f:
            pickle.dump(self, f)

        self.isUpdated = True

    def new_folder(self, path: str, name: str) -> None:
        logger.info(f"Creating new folder {name} in {path}")

        folder = Folder(name, path)
        if path == "/":
            directory_folder: Folder = self.contents[path]
            directory_folder.contents[folder.id] = folder
        else:
            paths = path.strip("/").split("/")
            directory_folder: Folder = self.contents["/"]
            for path in paths:
                directory_folder = directory_folder.contents[path]
            directory_folder.contents[folder.id] = folder

        self.save()

    def new_file(self, path: str, name: str, file_id: int, size: int) -> None:
        logger.info(f"Creating new file {name} in {path}")

        file = File(name, file_id, size, path)
        if path == "/":
            directory_folder: Folder = self.contents[path]
            directory_folder.contents[file.id] = file
        else:
            paths = path.strip("/").split("/")
            directory_folder: Folder = self.contents["/"]
            for path in paths:
                directory_folder = directory_folder.contents[path]
            directory_folder.contents[file.id] = file

        self.save()

    def get_directory(self, path: str) -> Folder:
        folder_data = self.contents["/"]
        if path != "/":
            path = path.strip("/")

            if "/" in path:
                path = path.split("/")
            else:
                path = [path]

            for folder in path:
                folder_data = folder_data.contents[folder]
        return folder_data

    def get_file(self, path) -> File:
        if len(path.strip("/").split("/")) > 0:
            folder_path = "/" + "/".join(path.strip("/").split("/")[:-1])
            file_id = path.strip("/").split("/")[-1]
        else:
            folder_path = "/"
            file_id = path.strip("/")

        folder_data = self.get_directory(folder_path)
        return folder_data.contents[file_id]

    def rename_file_folder(self, path: str, new_name: str) -> None:
        logger.info(f"Renaming {path} to {new_name}")

        if len(path.strip("/").split("/")) > 0:
            folder_path = "/" + "/".join(path.strip("/").split("/")[:-1])
            file_id = path.strip("/").split("/")[-1]
        else:
            folder_path = "/"
            file_id = path.strip("/")
        folder_data = self.get_directory(folder_path)
        folder_data.contents[file_id].name = new_name
        self.save()

    def trash_file_folder(self, path: str, trash: bool) -> None:
        logger.info(f"Trashing {path}")

        if len(path.strip("/").split("/")) > 0:
            folder_path = "/" + "/".join(path.strip("/").split("/")[:-1])
            file_id = path.strip("/").split("/")[-1]
        else:
            folder_path = "/"
            file_id = path.strip("/")
        folder_data = self.get_directory(folder_path)
        folder_data.contents[file_id].trash = trash
        self.save()

    def get_trashed_files_folders(self):
        root_dir = self.get_directory("/")
        trash_data = {}

        def traverse_directory(folder):
            for item in folder.contents.values():
                if item.type == "folder":
                    if item.trash:
                        trash_data[item.id] = item
                    else:
                        # Recursively traverse the subfolder
                        traverse_directory(item)
                elif item.type == "file":
                    if item.trash:
                        trash_data[item.id] = item

        traverse_directory(root_dir)
        return trash_data

    def delete_file_folder(self, path: str) -> None:
        logger.info(f"Deleting {path}")

        if len(path.strip("/").split("/")) > 0:
            folder_path = "/" + "/".join(path.strip("/").split("/")[:-1])
            file_id = path.strip("/").split("/")[-1]
        else:
            folder_path = "/"
            file_id = path.strip("/")

        folder_data = self.get_directory(folder_path)
        del folder_data.contents[file_id]
        self.save()


# Function to backup the drive data to telegram
async def backup_drive_data():
    global DRIVE_DATA
    logger.info("Starting backup drive data task")

    while True:
        await asyncio.sleep(DATABASE_BACKUP_TIME)  # Backup the data every 24 hours

        if DRIVE_DATA.isUpdated == False:
            continue

        logger.info("Backing up drive data to telegram")
        client = get_client()
        time_text = f"📅 **Last Updated :** {get_current_utc_time()} (UTC +00:00)"
        msg = await client.edit_message_media(
            STORAGE_CHANNEL,
            DATABASE_BACKUP_MSG_ID,
            media=InputMediaDocument(
                drive_cache_path,
                caption=f"🔐 **TG Drive Data Backup File**\n\nDo not edit or delete this message. This is a backup file for the tg drive data.\n\n{time_text}",
            ),
            file_name="drive.data",
        )
        try:
            await msg.pin()
        except:
            pass


async def loadDriveData():
    global DRIVE_DATA

    # Checking if the backup file exists on telegram
    client = get_client()
    try:
        try:
            msg = await client.get_messages(STORAGE_CHANNEL, DATABASE_BACKUP_MSG_ID)
        except:
            raise Exception("Failed to get DATABASE_BACKUP_MSG_ID on telegram")

        if msg.document.file_name == "drive.data":
            await msg.download(file_name=drive_cache_path)

            with open(drive_cache_path, "rb") as f:
                DRIVE_DATA = pickle.load(f)

            logger.info("Drive data loaded from backup file from telegram")
        else:
            raise Exception("Backup drive.data file not found on telegram")
    except Exception as e:
        logger.warning(e)
        logger.info("Creating new drive.data file")
        DRIVE_DATA = NewDriveData({"/": Folder("/", "/")}, [])
        DRIVE_DATA.save()
