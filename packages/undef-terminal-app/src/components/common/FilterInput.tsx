interface FilterInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function FilterInput({ value, onChange, placeholder = "Filter..." }: FilterInputProps) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{ width: 180, fontSize: 12, padding: "6px 10px" }}
    />
  );
}
