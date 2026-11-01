import re

class SRTParser:
    TIME_PATTERN = re.compile(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})")

    @staticmethod
    def parse(file_path: str) -> list:
        content = None
        for enc in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
            except Exception as e:
                print(f"Error reading file: {e!a}")
                return []

        if content is None:
            return []

        blocks = re.split(r'\n\s*\n', content.strip())
        subtitles = []

        for block in blocks:
            lines = block.split('\n')
            if len(lines) >= 3:
                try:
                    index = int(lines[0].strip())
                except ValueError:
                    continue

                time_match = SRTParser.TIME_PATTERN.search(lines[1])
                if not time_match:
                    continue

                start_time, end_time = time_match.groups()
                original_text = '\n'.join(lines[2:]).strip()

                subtitles.append({
                    "index": index,
                    "start_time": start_time,
                    "end_time": end_time,
                    "original": original_text,
                    "translation": "",
                    "status": "pending"
                })

        return subtitles
