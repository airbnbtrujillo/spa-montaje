/* Importa el XML del spot en el proyecto de Premiere abierto, guarda y deja un marcador. */
(function () {
    var C = {
    "project": "C:/Claude/spa-montaje/salida/premiere/Spot Spa.prproj",
    "xml": "C:/Claude/spa-montaje/salida/premiere/spot.xml",
    "marker": "C:/Claude/spa-montaje/salida/premiere/Spot Spa.importado.ok.txt",
    "error": "C:/Claude/spa-montaje/salida/premiere/Spot Spa.importado.error.txt",
    "sequence": "Spot Spa"
};
    function writeFile(path, text) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (f.open("w")) { f.write(text); f.close(); }
    }
    try {
        var marker = new File(C.marker);
        if (marker.exists) { $.writeln("Este paquete ya se importo: " + C.marker); return; }
        var xmlFile = new File(C.xml);
        if (!xmlFile.exists) { throw new Error("No encuentro el XML: " + C.xml); }
        if (!app.project) { throw new Error("No hay un proyecto abierto en Premiere."); }
        var before = app.project.sequences.numSequences;
        app.project.importFiles([xmlFile.fsName], true, app.project.rootItem, false);
        var seq = null, i;
        for (i = 0; i < app.project.sequences.numSequences; i++) {
            if (app.project.sequences[i].name == C.sequence) { seq = app.project.sequences[i]; }
        }
        if (!seq && app.project.sequences.numSequences > before) {
            seq = app.project.sequences[app.project.sequences.numSequences - 1];
        }
        if (!seq) { throw new Error("Premiere no dejo ninguna secuencia detectable tras importar el XML."); }
        try { app.project.openSequence(seq.sequenceID); } catch (e1) {}
        app.project.save();
        writeFile(C.marker, "OK\n" + (new Date()).toString() + "\nsecuencia: " + seq.name +
                  "\nproyecto: " + C.project + "\n");
    } catch (err) {
        writeFile(C.error, String(err));
        alert("No se pudo importar el XML en Premiere:\n" + String(err));
    }
})();
