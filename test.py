import re
text = """
Cyber-Physical System
 - Consistent definitions over time. Characteristics:
     - Hybrid Systems: hybrids of physical and logical elements
     - Hybrid Methods: join discrete and continuous methods for integrated physical and logical systems
     """

text = text.replace("\n", " ")
print(f"\nno indent text: {text}")
# remove excessive whitespace
text = re.sub(r"\s{2,}", " ", text)
print(f"\nno excessive whitespace: {text}")
text = text.replace(" - ", " ")
print(f"\nFinal text: {text}")

