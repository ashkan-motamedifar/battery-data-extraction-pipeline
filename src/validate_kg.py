import rdflib
import re

def load_graph(file_path):
    """Charge le graphe de connaissances (format Turtle)."""
    print(f"Chargement du graphe depuis {file_path}...")
    g = rdflib.Graph()
    try:
        g.parse(file_path, format="turtle")
        print(f"Graphe chargé avec succès : {len(g)} triplets trouvés.\n")
        return g
    except Exception as e:
        print(f"Erreur lors du chargement du graphe : {e}")
        return None

def check_voltage_inconsistencies(g):
    """Vérifie que : Tension Charge > Tension Nominale > Tension Décharge."""
    print("--- 1. Détection des incohérences de tension ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?chargeV ?nomV ?dischargeV
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   bat:hasChargeCutoffVoltage/bat:numericValue ?chargeV ;
                   bat:hasNominalVoltage/bat:numericValue ?nomV ;
                   bat:hasDischargeCutoffVoltage/bat:numericValue ?dischargeV .
                   
          FILTER (?chargeV <= ?nomV || ?nomV <= ?dischargeV || ?chargeV <= ?dischargeV)
        }
    """
    results = g.query(query)
    found = False
    for row in results:
        found = True
        print(f"❌ Incohérence sur la batterie {row.model} :")
        print(f"   Charge ({row.chargeV}V) | Nominale ({row.nomV}V) | Décharge ({row.dischargeV}V)")
        print("   Règle violée : La tension de charge doit être > nominale > décharge.")
    
    if not found:
        print("✅ Aucune incohérence de tension détectée.")
    print()

def check_out_of_range_values(g):
    """Vérifie si une cellule Li-Ion ou Li-Po a une tension nominale absurde."""
    print("--- 2. Détection des valeurs hors normes (Out-of-range) ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?chemLabel ?voltage
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   bat:hasChemistry ?chem ;
                   bat:hasNominalVoltage/bat:numericValue ?voltage .
          ?chem rdfs:label ?chemLabel .
          
          # Filtrer pour le Lithium et des tensions aberrantes pour une cellule seule
          FILTER ((?chem = bat:LiIon || ?chem = bat:LiPolymer) && (?voltage < 3.0 || ?voltage > 4.5))
        }
    """
    results = g.query(query)
    found = False
    for row in results:
        found = True
        print(f"⚠️ Valeur aberrante sur la batterie {row.model} ({row.chemLabel}) :")
        print(f"   Tension nominale extraite : {row.voltage}V")
        print("   Alerte : Une cellule au lithium standard a généralement une tension nominale entre 3.0V et 4.5V.")
    
    if not found:
        print("✅ Aucune valeur de tension hors normes détectée pour les cellules Lithium.")
    print()

def check_hallucinations(g):
    """Vérifie que la valeur numérique extraite est bien présente dans le texte source."""
    print("--- 3. Détection des hallucinations (Unsupported Statements) ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?qv ?value ?rawText
        WHERE {
          ?qv a bat:QuantityValue ;
              bat:numericValue ?value ;
              bat:rawText ?rawText .
        }
    """
    results = g.query(query)
    found = False
    
    for row in results:
        node, value, raw_text = row
        value_str = str(value)
        
        clean_value = value_str.rstrip('0').rstrip('.') if '.' in value_str else value_str
        
        if raw_text:
            text_str = str(raw_text)
            alternative_value = str(float(clean_value) / 1000).rstrip('0').rstrip('.') if len(clean_value) >= 4 else None
            
            match_exact = re.search(re.escape(clean_value), text_str)
            match_alt = alternative_value and re.search(re.escape(alternative_value), text_str)
            
            if not (match_exact or match_alt):
                found = True
                node_name = str(node).split('/')[-1]
                print(f"🚨 Hallucination potentielle détectée sur l'entité : {node_name}")
                print(f"   Valeur extraite par le LLM : {value_str}")
                print(f"   Texte source cité        : '{text_str}'")
                print("   -> La valeur n'apparaît pas clairement dans la citation.\n")
                
    if not found:
        print("✅ Aucune hallucination détectée (toutes les valeurs sont justifiées par leur texte brut).")
    print()

def check_negative_physical_values(g):
    """Vérifie que la capacité, le poids et la résistance sont strictement supérieurs à 0."""
    print("--- 4. Détection des valeurs physiques aberrantes (<= 0) ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?property ?value
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   ?property ?qv .
                   
          ?qv a bat:QuantityValue ;
              bat:numericValue ?value .
              
          # Filtrer uniquement sur les propriétés physiques qui ne peuvent pas être négatives
          FILTER (?property IN (bat:hasCapacity, bat:hasWeight, bat:hasInternalResistance))
          FILTER (?value <= 0)
        }
    """
    results = g.query(query)
    found = False
    
    for row in results:
        found = True
        prop_name = str(row.property).split('#')[-1] 
        print(f"❌ Valeur physiquement impossible sur la batterie {row.model} :")
        print(f"   La propriété '{prop_name}' a pour valeur : {row.value}")
        print("   Règle violée : Le poids, la capacité et la résistance doivent être strictement positifs.")
        
    if not found:
        print("✅ Aucune valeur physique négative ou nulle n'a été détectée.")
    print()

def check_missing_units(g):
    """Règle E : Vérifie que toute valeur quantitative possède bien une unité."""
    print("--- 5. Détection des unités manquantes (Structure) ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?property ?qv
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   ?property ?qv .
          ?qv a bat:QuantityValue .
          
          FILTER NOT EXISTS { ?qv bat:hasUnit ?unit }
        }
    """
    results = g.query(query)
    found = False
    for row in results:
        found = True
        prop_name = str(row.property).split('#')[-1]
        print(f"❌ Unité manquante sur la batterie {row.model} :")
        print(f"   La propriété '{prop_name}' a été extraite sans préciser d'unité.")
        
    if not found:
        print("✅ Toutes les grandeurs physiques possèdent bien une unité.")
    print()

def check_min_vs_typ_values(g):
    """Règle F : Vérifie que la valeur minimale n'est pas supérieure à la valeur typique."""
    print("--- 6. Détection d'incohérence : Valeur Minimale > Valeur Typique ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?property ?min ?typ
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   ?property ?qv .
                   
          ?qv a bat:QuantityValue ;
              bat:minimumValue ?min ;
              bat:numericValue ?typ .
              
          FILTER (?min > ?typ)
        }
    """
    results = g.query(query)
    found = False
    for row in results:
        found = True
        prop_name = str(row.property).split('#')[-1]
        print(f"❌ Incohérence Min/Typ sur la batterie {row.model} :")
        print(f"   Propriété '{prop_name}' -> Minimum garanti ({row.min}) > Valeur typique ({row.typ}).")
        
    if not found:
        print("✅ Aucune valeur minimale n'est supérieure à une valeur typique.")
    print()

def check_temperature_ranges(g):
    """Règle G : Vérifie que la plage de charge est incluse dans la plage de fonctionnement."""
    print("--- 7. Détection d'incohérence : Plages de températures ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?chMin ?chMax ?opMin ?opMax
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   bat:hasChargeTemperatureRange ?chRange ;
                   bat:hasOperatingTemperatureRange ?opRange .
                   
          ?chRange bat:minCelsius ?chMin ;
                   bat:maxCelsius ?chMax .
                   
          ?opRange bat:minCelsius ?opMin ;
                   bat:maxCelsius ?opMax .
                   
          # Erreur si on peut charger à une température où la batterie ne peut même pas fonctionner
          FILTER (?chMin < ?opMin || ?chMax > ?opMax)
        }
    """
    results = g.query(query)
    found = False
    for row in results:
        found = True
        print(f"❌ Incohérence de température sur la batterie {row.model} :")
        print(f"   Charge: [{row.chMin}°C, {row.chMax}°C] vs Opération: [{row.opMin}°C, {row.opMax}°C]")
        print("   Règle violée : La plage de charge doit être incluse dans la plage de fonctionnement.")
        
    if not found:
        print("✅ Les plages de températures de charge sont logiques par rapport aux plages globales.")
    print()

def check_coin_cell_weight(g):
    """Règle I : Vérifie qu'une pile bouton ne fait pas un poids absurde (> 30g)."""
    print("--- 8. Détection physique : Poids des piles boutons ---")
    query = """
        PREFIX bat: <http://battery-kg.org/ontology#>
        SELECT ?battery ?model ?weightVal
        WHERE {
          ?battery a bat:Battery ;
                   bat:modelName ?model ;
                   bat:hasFormFactor bat:Coin ;
                   bat:hasWeight ?weightNode .
                   
          ?weightNode bat:numericValue ?weightVal ;
                      bat:hasUnit bat:Gram .
                      
          FILTER (?weightVal > 30)
        }
    """
    results = g.query(query)
    found = False
    for row in results:
        found = True
        print(f"❌ Poids absurde détecté sur la batterie {row.model} :")
        print(f"   Format : Coin (Pile bouton) | Poids extrait : {row.weightVal}g")
        print("   Alerte : Une pile bouton standard dépasse rarement 10g à 20g.")
        
    if not found:
        print("✅ Aucun poids absurde détecté pour les piles boutons.")
    print()

if __name__ == "__main__":
    kg_file = "/home/kian/Bureau/DI/battery-data-extraction-pipeline/out/kg/battery_kg.ttl"
    graph = load_graph(kg_file)
    
    if graph:
        check_voltage_inconsistencies(graph)
        check_out_of_range_values(graph)
        check_hallucinations(graph)

        check_negative_physical_values(graph)

        check_missing_units(graph)
        check_min_vs_typ_values(graph)
        check_temperature_ranges(graph)
        check_coin_cell_weight(graph)