# Technocops DDC Converter Pro

## Non-Technical Conversion Summary (Hindi)

### यह software क्या करता है
Technocops DDC Converter Pro एक offline desktop application है जो OCR-generated HTML files, खासकर ABBYY FineReader output, को एक structured DTBook XML file में convert करता है।

यह software publishing workflow के लिए rule-based conversion करता है। यह AI की तरह अंदाज़ा लगाकर structure नहीं बनाता, बल्कि predefined rules follow करता है ताकि output consistent और predictable रहे।

### इसमें कौन-कौन सी technologies use हुई हैं
- Python
- Desktop interface के लिए PyQt6
- HTML parse करने, XML बनाने और DTD validation के लिए lxml
- GitHub update check के लिए requests
- Windows EXE बनाने के लिए PyInstaller

### Conversion कैसे होती है
Software पहले HTML files पढ़ता है, फिर content parse करता है, और उसके बाद fixed transformation rules apply करता है।

Conversion मुख्य रूप से इन चीज़ों पर आधारित है:
- HTML tag mapping
- ABBYY markers की पहचान जैसे page, pm, hsd, ol, ul
- Bold और italic text के लिए inline style detection
- Frontmatter, bodymatter, rearmatter, TOC और level IDs के लिए structural post-processing

### क्या conversion font-based है?
पूरी तरह नहीं।

यह converter MS Word या visual font appearance की तरह काम नहीं करता। यह मुख्य रूप से HTML tags और text markers पर आधारित है।

सिर्फ थोड़ा सा हिस्सा style-based है:
- bold span style को `strong` में convert किया जाता है
- italic span style को `em` में convert किया जाता है
- T1, T2, I, R जैसे special bold markers को `(T1)` जैसे bracket markers में बदला जाता है

### क्या conversion DTD-based है?
नहीं।

DTD conversion नहीं करती।

सबसे पहले application का rule engine conversion करता है। उसके बाद generated XML को DTBook structure और bundled DTD rules के against validate किया जाता है।

इसलिए DTD का काम validation है, transformation नहीं।

### Main conversion logic क्या है
- `<html>` structure को `dtbook`, `head`, `book`, `frontmatter`, `bodymatter`, और `rearmatter` में बदला जाता है
- metadata tags metadata form और detected document values से बनाए जाते हैं
- headings को nested `level1` से `level6` sections में convert किया जाता है
- `<ol>` और `<ul>` को DTBook `list` structure में बदला जाता है
- images को collect करके `imggroup` में reference किया जाता है
- tables को clean करके DTBook-friendly structure में रखा जाता है
- `<pm>` blocks को `linegroup` और `line` में convert किया जाता है
- `<hsd>` blocks को `sidebar` में convert किया जाता है
- page markers को `pagenum` में convert किया जाता है
- unsupported या forbidden HTML tags को rules के हिसाब से flatten या remove किया जाता है

### Validation और quality control
Conversion के बाद software इन चीज़ों की checking करता है:
- required DTBook sections
- required metadata
- leftover forbidden HTML tags
- XML well-formedness
- DTD validation issues

Software logs और error reports भी बनाता है ताकि operator warnings या structural problems review कर सके।

### Client ko batane ke liye one-line explanation
यह software `lxml` पर आधारित एक rule-based Python conversion engine use करता है जो ABBYY OCR HTML को structured DTBook XML में convert करता है, और conversion के बाद quality control के लिए DTD-based validation करता है।
