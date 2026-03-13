async function cargarTablas(){

let r = await fetch("/config/tablas")
let tablas = await r.json()

let contenedor = document.getElementById("modulos")

contenedor.innerHTML=""

tablas.forEach(t => {

let nombre = t[0]

let div = document.createElement("div")
div.className="modulo"

div.innerHTML = `

<h2>${nombre}</h2>
<div id="tabla_${nombre}"></div>
`

contenedor.appendChild(div)

cargarTabla(nombre)

})

}

async function cargarTabla(tabla){

    document.getElementById("titulo_tabla").innerText = "Tabla: " + tabla

    let r = await fetch("/config/tabla/" + tabla)
    let data = await r.json()

    let columnas = data.columnas
    let filas = data.datos

    let div = document.getElementById("tabla_editor")
    div.innerHTML = ""

    let table = document.createElement("table")

    // CABECERA
    let thead = document.createElement("tr")

    columnas.forEach(col=>{
        let th = document.createElement("th")
        th.innerText = col
        thead.appendChild(th)
    })

    table.appendChild(thead)

    // FILAS
    filas.forEach(row=>{

        let tr = document.createElement("tr")

        row.forEach(col=>{

            let td = document.createElement("td")
            td.contentEditable = true
            td.innerText = col

            tr.appendChild(td)

        })

        table.appendChild(tr)

    })

    div.appendChild(table)

}

window.onload = cargarTablas


function agregarFila(tabla,columnas){

let contenedor = document.getElementById("tabla_"+tabla)

let table = contenedor.querySelector("table")

let tr = document.createElement("tr")

for(let i=0;i<columnas;i++){

let td = document.createElement("td")

td.contentEditable = true

tr.appendChild(td)

}

table.appendChild(tr)

}

let guardar = document.createElement("button")

guardar.innerText = "💾 Guardar nueva fila"

guardar.onclick = () => guardarFila(tabla)

contenedor.appendChild(guardar)

async function guardarFila(tabla){

let contenedor = document.getElementById("tabla_"+tabla)

let filas = contenedor.querySelectorAll("tr")

let ultima = filas[filas.length-1]

let datos = []

ultima.querySelectorAll("td").forEach((td,i)=>{

if(i>0) datos.push(td.innerText)

})

await fetch("/config/tabla/"+tabla,{
method:"POST",
headers:{
"Content-Type":"application/json"
},
body:JSON.stringify(datos)
})

cargarTabla(tabla)

}

async function eliminarFila(tabla,id){

if(!confirm("Eliminar registro?")) return

await fetch(`/config/tabla/${tabla}/${id}`,{
method:"DELETE"
})

cargarTabla(tabla)

}

<script>

async function cargarTablas(){

let r = await fetch("/config/tablas_lista")

let tablas = await r.json()

let div = document.getElementById("tabs_tablas")

div.innerHTML=""

tablas.forEach(t=>{

let btn = document.createElement("button")

btn.innerText = t

btn.onclick = ()=> cargarTabla(t)

btn.className = "tab-btn"

div.appendChild(btn)

})

}

cargarTablas()

</script>