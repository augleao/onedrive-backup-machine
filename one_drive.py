import os
import aiohttp
import asyncio
from typing import List, Dict

GRAPH_BASE = 'https://graph.microsoft.com/v1.0'

async def list_folder(access_token: str, folder_path: str = 'Backups') -> List[Dict]:
    headers = {'Authorization': f'Bearer {access_token}'}
    # folder_path should be relative, e.g., 'Backups' or 'Backups/HomeAssistant'
    url = f"{GRAPH_BASE}/me/drive/root:/{folder_path}:/children"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f'Graph list error: {resp.status} {text}')
            data = await resp.json()
            return data.get('value', [])


async def download_item(access_token: str, item_id: str, dest_path: str, overwrite: bool = True, progress_cb=None) -> Dict:
    headers = {'Authorization': f'Bearer {access_token}'}
    url = f"{GRAPH_BASE}/me/drive/items/{item_id}/content"
    os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
    tmp_path = dest_path + '.part'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f'Graph download error: {resp.status} {text}')
            # Stream to file
            mode = 'wb'
            total = resp.content_length or 0
            downloaded = 0
            with open(tmp_path, mode) as f:
                async for chunk in resp.content.iter_chunked(65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        try:
                            await progress_cb(downloaded, total)
                        except Exception:
                            pass
    # Move tmp to final
    if os.path.exists(dest_path):
        if overwrite:
            os.remove(dest_path)
        else:
            os.remove(tmp_path)
            return {'path': dest_path, 'status': 'skipped'}
    os.replace(tmp_path, dest_path)
    return {'path': dest_path, 'status': 'completed'}
