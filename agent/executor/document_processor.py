"""
Document Processor - Intelligent Document Analysis Engine (Phase 37)
Handles PDF, Word, Excel, and Text files with "Read-on-Demand" and "Encoding Sentinel" protocols.
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """
    智能文档处理器
    
    职责：
    - 文档地图生成 (Metadata, Outline, Summary)
    - 分片读取 (Paging, Keyword Slicing)
    - 结构化转换 (Excel to MD)
    - 编码自动检测 (Encoding Sentinel)
    """
    
    def __init__(self):
        # 内部缓存由 TaskOrchestrator 统一管理，此处保留轻量化
        pass

    def get_document_map(self, file_path: str) -> Dict[str, Any]:
        """
        返回文档“地图”：页数、大纲、摘要片段 (Protocol R1)
        """
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": f"文件不存在: {file_path}"}

        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                return self._map_pdf(path)
            elif ext in [".docx", ".doc"]:
                return self._map_docx(path)
            elif ext in [".xlsx", ".xls", ".csv"]:
                return self._map_spreadsheet(path)
            else:
                return self._map_text(path)
        except Exception as e:
            logger.error(f"生成文档地图失败 ({file_path}): {e}")
            return {"error": str(e)}

    def read_specific_chunk(self, file_path: str, page_num: Optional[int] = None, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        精准分片读取逻辑 (Protocol R1)
        """
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return {"error": "文件不存在"}

        ext = path.suffix.lower()
        try:
            if ext == ".pdf":
                return self._read_pdf_chunk(path, page_num, keywords)
            elif ext in [".xlsx", ".xls", ".csv"]:
                return self._read_spreadsheet_all(path) # 表格通常整体转换
            else:
                return self._read_text_full(path)
        except Exception as e:
            logger.error(f"分片读取失败: {e}")
            return {"error": str(e)}

    # --- PDF 处理器 ---
    def _map_pdf(self, path: Path) -> Dict[str, Any]:
        try:
            import pypdf
            with open(path, "rb") as f:
                reader = pypdf.PdfReader(f)
                num_pages = len(reader.pages)
                # 获取简单的文本摘要
                preview = ""
                if num_pages > 0:
                    preview = reader.pages[0].extract_text()[:500]
                
                return {
                    "type": "pdf",
                    "pages": num_pages,
                    "preview": preview,
                    "outline": self._extract_pdf_outline(reader)
                }
        except ImportError:
            return {"error": "需要安装 pypdf: pip install pypdf"}

    def _extract_pdf_outline(self, reader) -> List[str]:
        try:
            outline = []
            for item in reader.outline:
                if isinstance(item, dict) and "/Title" in item:
                    outline.append(item["/Title"])
                elif isinstance(item, list):
                    continue # 暂时只取一级大纲
            return outline[:10]
        except Exception:
            return []

    def _read_pdf_chunk(self, path: Path, page_num: Optional[int], keywords: Optional[List[str]]) -> Dict[str, Any]:
        import pypdf
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(f)
            if page_num is not None:
                # 指定页读取
                if 1 <= page_num <= len(reader.pages):
                    text = reader.pages[page_num - 1].extract_text()
                    return {"page": page_num, "content": text}
                else:
                    return {"error": f"页码超出范围: {page_num}"}
            
            if keywords:
                # 关键词匹配读取
                hits = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if any(k.lower() in text.lower() for k in keywords):
                        hits.append({"page": i+1, "content": text})
                    if len(hits) >= 3:
                        break  # 限制返回量
                return {"hits": hits}
            
            # 默认返回第一页
            return {"page": 1, "content": reader.pages[0].extract_text()}

    # --- Word 处理器 ---
    def _map_docx(self, path: Path) -> Dict[str, Any]:
        try:
            import docx
            doc = docx.Document(path)
            paragraphs = doc.paragraphs
            preview = "\n".join([p.text for p in paragraphs[:5]])[:500]
            return {
                "type": "docx",
                "paragraphs": len(paragraphs),
                "preview": preview
            }
        except ImportError:
            return {"error": "需要安装 python-docx: pip install python-docx"}

    # --- 表格处理器 (Protocol R2: Excel to MD) ---
    def _map_spreadsheet(self, path: Path) -> Dict[str, Any]:
        return {
            "type": "spreadsheet",
            "extension": path.suffix,
            "message": "表格文件建议使用 analyze 操作进行结构化转换"
        }

    def _read_spreadsheet_all(self, path: Path) -> Dict[str, Any]:
        try:
            import pandas as pd
            if path.suffix.lower() == ".csv":
                encoding = self._detect_encoding(path)
                df = pd.read_csv(path, encoding=encoding)
            else:
                df = pd.read_excel(path)
            
            # 转换为 Markdown Table (Protocol R2)
            md_table = df.head(50).to_markdown() # 限制 50 行防止溢出
            return {
                "type": "markdown_table",
                "rows": len(df),
                "content": md_table
            }
        except ImportError:
            return {"error": "需要安装 pandas 和 openpyxl: pip install pandas openpyxl"}

    # --- 文本处理器 (Protocol Encoding Sentinel) ---
    def _map_text(self, path: Path) -> Dict[str, Any]:
        encoding = self._detect_encoding(path)
        with open(path, "r", encoding=encoding, errors='ignore') as f:
            content = f.read(1000)
        return {
            "type": "text",
            "encoding": encoding,
            "preview": content
        }

    def _read_text_full(self, path: Path) -> Dict[str, Any]:
        encoding = self._detect_encoding(path)
        with open(path, "r", encoding=encoding, errors='ignore') as f:
            content = f.read()
        return {"content": content}

    def _detect_encoding(self, path: Path) -> str:
        """
        编码检测哨兵 (Encoding Sentinel)
        """
        try:
            import chardet
            with open(path, "rb") as f:
                raw = f.read(10240)
                result = chardet.detect(raw)
                return result['encoding'] or 'utf-8'
        except ImportError:
            return "utf-8"
        except Exception:
            return "utf-8"
