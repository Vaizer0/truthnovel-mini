const cleanOut = function (o) {
  let t = String(o || "").trim();
  t = t.replace(/^```[a-z]*\s*/i, "").replace(/\s*```$/, "").trim();
  t = t.replace(/^(?:[*_#>`\s]|\*\*|__)*(?:sure[,!.\s]*)?(?:here(?:\s+is|'s|’s)\b[^\n:]{0,80}:|translation:|translated text:|english:)(?:[*_`\s:]|\*\*|__)*\s*/i, "").trim();
  t = t.replace(/\*\*|__/g, "");
  const ps = t.split(/\n{2,}/);
  while (ps.length > 1 && /^\s*(?:[*_#>`\s-])*(translator'?s?\s+note|notes?|hope (this|that)|let me know|disclaimer|if you (need|want)|i hope|feel free)(?:[*_`\s:.-])*[:\s]/i.test(ps[ps.length - 1])) ps.pop();
  return ps.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
};

const cases = [
  ["**Here is the translation:**\n\nHe drew his sword slowly.", "He drew his sword slowly."],
  ["```\n**Translation:**\n\nThe sky was dark.\n```", "The sky was dark."],
  ["The wind howled.\n\nTranslator note: I kept the tone flat.\n\nHope this helps!", "The wind howled."],
  ["Sure, here is the translation:\n\nFirst para.\n\nSecond para.", "First para.\n\nSecond para."],
  ["Just a plain paragraph.", "Just a plain paragraph."],
  ["**Bold start**\n\nSecond **bold** para.", "Bold start\n\nSecond bold para."],
  ["", ""],
];

let pass = 0;
for (const [input, expected] of cases) {
  const got = cleanOut(input);
  const ok = got === expected;
  if (ok) pass++;
  console.log((ok ? "ok  " : "FAIL") + " -> " + JSON.stringify(got) + (ok ? "" : "   expected " + JSON.stringify(expected)));
}
console.log("\n" + pass + "/" + cases.length + " sanitizer cases passed");
