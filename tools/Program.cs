using Mono.Cecil;
using Mono.Cecil.Cil;

var signaturesOnly = args.Length >= 1 && args[0] == "--signatures";
var exactMethodsOnly = args.Length >= 1 && args[0] == "--methods";
var argumentOffset = signaturesOnly || exactMethodsOnly ? 1 : 0;
if (args.Length < argumentOffset + 2)
{
    Console.Error.WriteLine("usage: inspect_managed_methods [--signatures|--methods] <assembly> <term> [term ...]");
    return 2;
}

var assemblyPath = args[argumentOffset];
var terms = args.Skip(argumentOffset + 1).ToArray();
var assembly = AssemblyDefinition.ReadAssembly(assemblyPath);
foreach (var type in Flatten(assembly.MainModule.Types))
{
    if (signaturesOnly)
    {
        foreach (var method in type.Methods.Where(method =>
                     terms.Any(term => string.Equals(method.Name, term, StringComparison.Ordinal))))
        {
            Console.WriteLine(method.FullName);
        }
        continue;
    }
    if (!exactMethodsOnly && terms.Any(term => type.FullName.Contains(term, StringComparison.OrdinalIgnoreCase)))
    {
        Console.WriteLine($"\n### TYPE {type.FullName}");
        foreach (var field in type.Fields)
        {
            Console.WriteLine($"FIELD {field.FieldType.FullName} {field.Name}");
        }
        foreach (var property in type.Properties)
        {
            Console.WriteLine($"PROPERTY {property.PropertyType.FullName} {property.Name}");
        }
    }
    foreach (var method in type.Methods.Where(m => m.HasBody))
    {
        var haystack = string.Join("\n", method.Body.Instructions.Select(FormatInstruction));
        var selected = exactMethodsOnly
            ? terms.Any(term => string.Equals(method.Name, term, StringComparison.Ordinal))
            : terms.Any(term =>
                method.FullName.Contains(term, StringComparison.OrdinalIgnoreCase) ||
                haystack.Contains(term, StringComparison.OrdinalIgnoreCase));
        if (!selected)
        {
            continue;
        }
        Console.WriteLine($"\n=== {method.FullName} ===");
        foreach (var instruction in method.Body.Instructions)
        {
            Console.WriteLine(FormatInstruction(instruction));
        }
    }
}

return 0;

static IEnumerable<TypeDefinition> Flatten(IEnumerable<TypeDefinition> types)
{
    foreach (var type in types)
    {
        yield return type;
        foreach (var nested in Flatten(type.NestedTypes)) yield return nested;
    }
}

static string FormatInstruction(Instruction instruction)
{
    var operand = instruction.Operand switch
    {
        MethodReference method => method.FullName,
        FieldReference field => field.FullName,
        TypeReference type => type.FullName,
        string text => "\"" + text.Replace("\r", "\\r").Replace("\n", "\\n") + "\"",
        null => string.Empty,
        _ => instruction.Operand.ToString() ?? string.Empty
    };
    return $"IL_{instruction.Offset:X4}: {instruction.OpCode,-12} {operand}";
}
