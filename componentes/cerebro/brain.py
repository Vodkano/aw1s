import os
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any

from langchain_ollama import OllamaLLM
from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

try:
    from .wikipedia_service import WikipediaService
except ImportError:
    from wikipedia_service import WikipediaService

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OLLAMA_MODEL = "llama3.2:latest"
DEFAULT_GPT_MODEL = "gpt-4.1-mini"
OLLAMA_RESPONSE_PROMPT = (
    "Eres un agente virtual de IA local. Responde a la pregunta del usuario "
    "de forma clara y util. No devuelvas una decision de enrutamiento ni JSON "
    "salvo que el usuario lo solicite. Si entregas codigo, encerralo en un "
    "bloque Markdown con el lenguaje, por ejemplo ```python."
)


def load_prompt(prompt_path: str | Path) -> str:
    """Carga un prompt relativo al directorio de este modulo."""
    path = Path(prompt_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.read_text(encoding="utf-8")


class BrainOllama:
    def __init__(
        self,
        model: str | None = None,
        prompt_path: str = "ollama_promt_master.txt",
    ):
        model = model or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
        self.client = OllamaLLM(model=model)
        self.model = model
        self.system_prompt = load_prompt(prompt_path)
        self.history = []

    def ask(self, message: str) -> dict[str, Any]:
        """Analiza la entrada y devuelve la decision JSON validada."""
        self._validate_message(message)
        self.history.append({"role": "user", "content": message})
        prompt = f"{self.system_prompt}\n\nUsuario: {message}\nAsistente:"
        answer = self._invoke(prompt)
        self.history.append({"role": "assistant", "content": answer})
        return self._parse_json(answer)

    @staticmethod
    def _validate_message(message: str) -> None:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("El mensaje debe ser un texto no vacio.")

    def _invoke(self, prompt: str) -> str:
        try:
            return self.client.invoke(prompt)
        except Exception as error:
            if "not found" in str(error).lower():
                raise RuntimeError(
                    f"El modelo Ollama '{self.model}' no esta instalado. "
                    f"Instala uno con: ollama pull {self.model}"
                ) from error
            raise

    @staticmethod
    def _parse_json(answer):
        cleaned = answer.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```").removeprefix("json").strip()
            cleaned = cleaned.removesuffix("```").strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as error:
            raise ValueError("Ollama no devolvio un JSON valido.") from error
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("puede_responder"), bool)
            or result.get("modelo") not in {"ollama", "gpt"}
            or result.get("fuente", "modelo") not in {"modelo", "wikipedia"}
            or (
                result["puede_responder"] and result["modelo"] != "ollama"
            )
            or (
                not result["puede_responder"]
                and result.get("fuente", "modelo") == "modelo"
                and result["modelo"] != "gpt"
            )
        ):
            raise ValueError(
                "El JSON debe incluir puede_responder (booleano) y "
                "modelo y fuente coherentes con la decision."
            )
        return result

    def respond(self, message: str) -> str:
        """Genera la respuesta visible para el usuario."""
        self._validate_message(message)
        prompt = f"{OLLAMA_RESPONSE_PROMPT}\n\nUsuario: {message}\nAsistente:"
        return self._invoke(prompt)


class BrainGPT:
    def __init__(
        self,
        model: str = DEFAULT_GPT_MODEL,
        prompt_path: str = "promt.path",
    ):
        self.client = OpenAI(api_key=self._load_api_key())
        self.model = model
        self.system_prompt = load_prompt(prompt_path)
        self.history = []

    @staticmethod
    def _load_api_key():
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key

        try:
            return subprocess.check_output(
                ["security", "find-generic-password", "-s", "openai-api-key", "-w"],
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                "Configura OPENAI_API_KEY o guarda la clave en el llavero "
                "con el servicio 'openai-api-key'."
            )

    def ask(self, message: str) -> str:
        BrainOllama._validate_message(message)
        self.history.append({"role": "user", "content": message})
        response = self.client.responses.create(
            model=self.model,
            instructions=self.system_prompt,
            input=self.history,
        )
        answer = response.output_text
        self.history.append({"role": "assistant", "content": answer})
        return answer


class Brain:
    """Recibe todo por Ollama y activa GPT solo cuando es necesario."""

    def __init__(
        self,
        ollama: BrainOllama | None = None,
        gpt: BrainGPT | None = None,
        wikipedia: WikipediaService | None = None,
    ):
        self.ollama = ollama or BrainOllama()
        self.gpt = gpt
        self.wikipedia = wikipedia or WikipediaService()
        self.analysis_result: dict[str, Any] | None = None

    def ask(self, message: str) -> str:
        return self.ask_result(message)["answer"]

    def ask_result(self, message: str) -> dict[str, Any]:
        """Devuelve la respuesta visible y metadatos para la interfaz."""
        BrainOllama._validate_message(message)
        try:
            self.analysis_result = self.ollama.ask(message)
        except ValueError:
            self.analysis_result = {
                "puede_responder": True,
                "modelo": "ollama",
                "fuente": "modelo",
                "busqueda": "",
                "motivo": "clasificacion local no estructurada",
            }
        if self._looks_like_person_query(message):
            self.analysis_result = {
                **self.analysis_result,
                "puede_responder": False,
                "modelo": "ollama",
                "fuente": "wikipedia",
                "busqueda": self._person_search_term(message),
                "motivo": "consulta biografica detectada",
            }
        if self.analysis_result.get("fuente") == "wikipedia":
            search_term = self.analysis_result.get("busqueda", message)
            return self._response_payload(self.wikipedia.answer(search_term))
        if self.analysis_result["puede_responder"]:
            return self._response_payload(self.ollama.respond(message))
        if self.analysis_result["modelo"] == "gpt":
            if self.gpt is None:
                self.gpt = BrainGPT()
            try:
                return self._response_payload(self.gpt.ask(message))
            except (
                APIConnectionError,
                APIStatusError,
                AuthenticationError,
                RateLimitError,
            ):
                return self._response_payload(self.ollama.respond(message))
        raise RuntimeError("Ningun motor fue seleccionado para responder.")

    @staticmethod
    def _response_payload(answer: str) -> dict[str, Any]:
        """Extrae un bloque Markdown de codigo sin alterar el texto original."""
        match = re.search(r"```([A-Za-z0-9_+-]*)\s*\n?(.*?)```", answer, re.DOTALL)
        if not match:
            return {"answer": answer, "is_code": False, "language": "", "code": ""}
        language = match.group(1).lower() or "text"
        code = match.group(2).strip()
        visible_text = (answer[:match.start()] + answer[match.end():]).strip()
        return {
            "answer": visible_text or "Codigo generado por el modelo.",
            "is_code": True,
            "language": language,
            "code": code,
        }

    @staticmethod
    def _looks_like_person_query(message: str) -> bool:
        normalized = Brain._normalize_text(message)
        markers = (
            "quien fue ",
            "quien es ",
            "quien era ",
            "biografia de ",
            "hablame de ",
            "datos sobre ",
        )
        return any(normalized.startswith(marker) for marker in markers)

    @staticmethod
    def _normalize_text(message: str) -> str:
        normalized = "".join(
            character
            for character in unicodedata.normalize("NFD", message.lower())
            if unicodedata.category(character) != "Mn"
        )
        return normalized.lstrip(" ¿¡\t")

    @classmethod
    def _person_search_term(cls, message: str) -> str:
        normalized = cls._normalize_text(message)
        markers = (
            "quien fue ",
            "quien es ",
            "quien era ",
            "biografia de ",
            "hablame de ",
            "datos sobre ",
        )
        for marker in markers:
            if normalized.startswith(marker):
                return message.lstrip(" ¿¡\t")[len(marker):].strip(" ?!.,")
        return message.strip(" ?!.,")


if __name__ == "__main__":
    brain = Brain()
    print(brain.ask(input("Mensaje: ")))
