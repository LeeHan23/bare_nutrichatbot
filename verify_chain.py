from chain_factory import get_behavior_template

try:
    template = get_behavior_template("Diabetes")
    print("Successfully generated template.")
    print(template[:100]) # Print first 100 chars
except Exception as e:
    print(f"Error generating template: {e}")
