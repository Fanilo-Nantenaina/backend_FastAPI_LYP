from fastapi import FastAPI, File, UploadFile, HTTPException
import json
import io
from PIL import Image
from datetime import datetime
from typing import List, Dict, Any
from google import genai
from google.genai import types
import os

from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Smart Fridge API", version="6.0 - Gemini API Integration")

print("🔧 Initialisation de l'API Gemini...")

try:
    client = genai.Client()
    GEMINI_MODEL = "gemini-2.5-flash"
    print(f"Client Gemini prêt. Modèle utilisé : {GEMINI_MODEL}")
except Exception as e:
    print(f"Erreur d'initialisation de Gemini : {e}")
    client = None

# --- Schéma de sortie JSON désiré ---
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "detected_products": {
            "type": "array",
            "description": "Liste de tous les produits alimentaires identifiés dans l'image.",
            "items": {
                "type": "object",
                "properties": {
                    "product": {
                        "type": "string",
                        "description": "Nom spécifique du produit (ex: 'Tomate cerise', 'Brique de lait (marque X)').",
                    },
                    "category": {
                        "type": "string",
                        "description": "Catégorie générale du produit (ex: 'Légume', 'Fruit', 'Laitier', 'Épicerie').",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Nombre d'unités de ce produit détectées (pour les objets en vrac comme les carottes ou les œufs).",
                    },
                    "packaging_text": {
                        "type": "string",
                        "description": "Texte principal lu sur l'emballage ou la boîte de conserve (utilisé comme OCR).",
                    },
                },
                "required": ["product", "category", "count", "packaging_text"],
            },
        },
        "notes": {
            "type": "string",
            "description": "Toute remarque pertinente sur l'image (faible qualité, produit illisible, etc.).",
        },
    },
    "required": ["detected_products", "notes"],
}

# --- PROMPT INSTRUCTIONS ---
SYSTEM_INSTRUCTION = (
    "Vous êtes un assistant expert en inventaire de cuisine. Analysez l'image fournie, peu importe "
    "le placement aléatoire des objets (frigo, main, sol). L'image peut être de faible qualité et "
    "contenir de nombreux petits objets (comptez-les avec précision). "
    "Utilisez la reconnaissance de texte (OCR) pour extraire le nom des produits emballés et "
    "remplir le champ 'packaging_text'. Répondez UNIQUEMENT en format JSON structuré selon le schéma fourni."
)


@app.post("/analyze")
async def analyze_image(file: UploadFile = File(...)):
    """
    Analyse l'image en utilisant l'API Gemini pour la détection, le comptage et l'OCR ciblée.
    """
    if not client:
        raise HTTPException(503, "L'API Gemini n'est pas configurée.")

    try:
        # 1. Lecture et conversion de l'image pour l'API Gemini
        contents = await file.read()
        image = Image.open(io.BytesIO(contents))

        # 2. Création de la requête
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=OUTPUT_SCHEMA,
        )

        # Le contenu est l'instruction + l'image
        contents_list = [
            image,
            "Inventoriez tous les produits alimentaires visibles. Comptez précisément les produits en vrac ou les petits objets (ex: tomates cerises, œufs, carottes). Pour les boîtes, lisez le nom du produit sur l'emballage.",
        ]

        # 3. Appel de l'API
        print("🌍 Appel à l'API Gemini pour l'analyse et le comptage...")
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents_list,
            config=config,
        )

        # 4. Traitement de la réponse JSON
        # La réponse de Gemini est directement une chaîne JSON valide
        if not response.text:
            raise HTTPException(500, "L'API Gemini n'a pas retourné de JSON structuré.")

        data = json.loads(response.text)

        # 5. Mise en forme du résultat final
        inventory_update = {
            d["product"]: d["count"] for d in data.get("detected_products", [])
        }

        final_results = {
            "timestamp": datetime.now().isoformat(),
            "detected_products": data.get("detected_products", []),
            "cleaned_count": sum(d["count"] for d in data.get("detected_products", [])),
            "inventory_update": inventory_update,
            "gemini_notes": data.get("notes", "Aucune note spécifique de l'IA."),
        }

        # NOTE: La détection de BBOX et l'image de debug ne sont pas disponibles ici,
        # car Gemini ne retourne pas les coordonnées des boîtes pour ce type de requête structurée.
        # Si vous avez besoin des BBOX, vous devriez utiliser la fonction
        # 'gemini.models.generate_content' avec 'detection' et 'localization'.

        return final_results

    except json.JSONDecodeError:
        print(f"Erreur de décodage JSON: Réponse brute: {response.text}")
        raise HTTPException(500, "Erreur de format de réponse de l'IA (JSON invalide).")
    except Exception as e:
        print(f"Erreur générale d'analyse: {e}")
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
