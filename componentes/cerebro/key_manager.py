import getpass
import os
import subprocess


KEYCHAIN_SERVICE = "openai-api-key"
ACCOUNT = os.environ.get("USER", "openai")


def delete_key() -> bool:
    result = subprocess.run(
        ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("Clave anterior eliminada.")
        return True
    if "could not be found" in result.stderr.lower():
        print("No había una clave guardada.")
        return False
    raise RuntimeError(result.stderr.strip() or "No se pudo acceder al llavero.")


def save_key() -> None:
    api_key = getpass.getpass("Nueva clave API: ").strip()
    if not api_key:
        print("No se guardó una clave vacía.")
        return

    subprocess.run(
        [
            "security",
            "add-generic-password",
            "-a",
            ACCOUNT,
            "-s",
            KEYCHAIN_SERVICE,
            "-w",
            api_key,
            "-U",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    print("Nueva clave guardada en el llavero de macOS.")


def main() -> None:
    print("1. Guardar o reemplazar clave API")
    print("2. Borrar clave API")
    option = input("Selecciona una opción: ").strip()

    if option == "1":
        save_key()
    elif option == "2":
        delete_key()
    else:
        print("Opción no válida.")


if __name__ == "__main__":
    main()
