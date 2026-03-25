window.mermaid?.initialize({
  startOnLoad: true,
  theme: "neutral",
  flowchart: {
    htmlLabels: true,
    useMaxWidth: true,
  },
});

if (typeof document$ !== "undefined") {
  document$.subscribe(() => {
    window.mermaid?.run();
  });
}