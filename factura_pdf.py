from datetime import date, datetime
import os
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import  A4,letter
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image
from reportlab.lib.styles import getSampleStyleSheet
from decimal import Decimal
 
import streamlit as st
from database import (get_facturas, insertar_detalle_factura, insertar_factura, obtener_cliente_por_nombre, obtener_nombre_cliente_por_id,
                      obtener_nombre_servicio_por_id, create_server_connection, obtener_total_factura, servicio_asignados_cliente, factura_ya_existe)
 

# Configuración de la página de Streamlit
st.set_page_config(page_title="Factura de Venta", layout="wide")


def obtener_nombre_servicio(service_id, connection):
    """Obtiene el nombre del servicio a partir de su ID."""
    return obtener_nombre_servicio_por_id(service_id, connection)

# Función para generar el PDF usando ReportLab
def generar_factura_pdf(cliente_id, servicios_asignados, fecha_factura, total, descuento, factura_id, connection):
    pdf_dir = './facturas_generadas'
    
    cliente_info = obtener_nombre_cliente_por_id(cliente_id, connection)
    # Verificar y convertir fecha_factura a un objeto datetime si es necesario
    if isinstance(fecha_factura, int):
        fecha_factura = datetime.fromtimestamp(fecha_factura)
        
    # Cargar la fecha actual
    fecha_factura = date.today()

    # Configuración inicial del documento PDF
    file_name = f"factura-{cliente_info.replace(' ', '_')}-{fecha_factura.strftime('%Y%m%d')}.pdf"
    document = SimpleDocTemplate(file_name, pagesize=A4)
    story = []
    styles = getSampleStyleSheet()

    # Añadir el logo
    im = Image('assets/logo.png', 2*inch, 1*inch)
    im.hAlign = 'LEFT'
    story.append(im)
    story.append(Spacer(1, 2*cm))

    # Añadir el título de la factura
    style = styles['Title']
    story.append(Paragraph("FACTURA", style))
    story.append(Spacer(1, 12))

    # Añadir la fecha de la factura
    style = styles['Normal']
    story.append(Paragraph(f"Fecha: {fecha_factura.strftime('%d/%m/%Y')}", style))
    story.append(Spacer(1, 12))
    
    # Añadir el número de factura
    style = styles['Normal']
    story.append(Paragraph(f"Número de Factura: {factura_id}", style))
    story.append(Spacer(1, 12))


    # Añadir la información del cliente
    cliente_info = obtener_nombre_cliente_por_id(cliente_id, connection)
    story.append(Paragraph(f"Cliente: {cliente_info}", style))
    story.append(Spacer(1, 0.5*cm))

   # Crear y añadir la tabla de servicios
    encabezados = [('Descripción de los Servicios', 'Cantidad', 'Precio')]
    # Suponiendo que la estructura de cada tupla sea:
# (id_servicio, cantidad, precio)
    servicios_data = [encabezados[0]] + [(obtener_nombre_servicio(s[1], connection), s[2], f"${s[3]:,.2f}") for s in servicios_asignados]


    t = Table(servicios_data, colWidths=[3*inch, inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f8f8ff")),  # Fondo del encabezado
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),  # Color del texto del encabezado
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Alineación del texto en todas las celdas
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  # Fuente del encabezado
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),  # Relleno inferior del encabezado
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),  # Fondo del resto de la tabla
        ('BOX', (0, 0), (-1, -1), 1, colors.black),  # Añade un borde alrededor de toda la tabla
        ('GRID', (0, 0), (-1, -1), 1, colors.black),  # Añade líneas de la tabla
    ]))
    story.append(t)
    # Añadir el subtotal, descuento y total final
    descuento_decimal = Decimal(descuento) if not isinstance(descuento, Decimal) else descuento
    descuento_aplicado = total * (descuento_decimal / Decimal('100'))
    total_final = total - descuento_aplicado
    datos_totales = [
        ['Subtotal', f"${total:,.2f}"],
        [f"Descuento ({descuento}%)", f"-${descuento_aplicado:,.2f}"],
        ['Total Final', f"${total_final:,.2f}"]
    ]
    t_totals = Table(datos_totales, colWidths=[None, 2*inch])
    t_totals.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(t_totals)

    # Construir y guardar el PDF
    document.build(story)
    return file_name


def mostrar_previsualizacion(connection):
    """Muestra una previsualización de la factura en la interfaz de usuario."""    
    datos = st.session_state.get('previsualizacion_datos', {})
    if datos:
        st.subheader("Previsualización de la Factura")
        st.write(f"Cliente: {datos['nombre_cliente']}")
        for servicio in datos['servicios_asignados']:
            nombre_servicio = obtener_nombre_servicio(servicio[1], connection)# servicio[0] es id_servicio
            cantidad_servicio = servicio[2]  # servicio[1] es cantidad
            precio_servicio = servicio[3]  # servicio[2] es precio
            st.write(f"Servicio: {nombre_servicio} - Cantidad: {cantidad_servicio} - Precio: {precio_servicio}")


        st.write(f"Total antes de descuento: {datos['total']}")
        st.write(f"Descuento: {datos['descuento']}%")
        descuento_decimal = Decimal(str(datos['descuento']))
        total_con_descuento = datos['total'] * (1 - (descuento_decimal / 100))
        st.write(f"Total después de descuento: {total_con_descuento}")


# Función para mostrar el botón de descarga del PDF
def mostrar_factura_pdf(pdf_file, servicios_asignados, connection):
    with open(pdf_file, "rb") as f:
        st.download_button(label="Descargar Factura", data=f, file_name="factura.pdf", mime="application/pdf")
        st.write("Servicios:")
        for servicio in servicios_asignados:
           id_servicio = servicio[1]
           cantidad = servicio[2]
           precio = servicio[3]
           nombre_servicio = obtener_nombre_servicio(id_servicio, connection)
           st.write(f"Nombre: {nombre_servicio} - Cantidad: {cantidad} - Precio: {precio}")
          
# .............................................................................
def generar_factura_final():
    datos = st.session_state.get('previsualizacion_datos', {})
    if datos:
        connection = create_server_connection("localhost", "root", "123", "lucmonet")
        cliente_id = datos['cliente_id']
        servicios_asignados = datos['servicios_asignados']
        total = datos['total']
        descuento = datos['descuento']
        fecha_factura = datos['fecha_factura']  # Asegúrate de que esta fecha se esté obteniendo correctamente

        # Llamada a la función modificada con todos los argumentos necesarios
        factura_id = insertar_factura(cliente_id, total, descuento, fecha_factura, connection)

        if factura_id:
            for servicio in servicios_asignados:
                insertar_detalle_factura(factura_id, servicio[1], servicio[2], servicio[3], total, cliente_id, descuento, connection)

            pdf_file = generar_factura_pdf(cliente_id, servicios_asignados, fecha_factura, total, descuento, factura_id, connection)
            mostrar_factura_pdf(pdf_file, servicios_asignados, connection)
            st.success("Factura generada y guardada con éxito.")
        else:
            st.error("Error al insertar factura en la base de datos.")
    else:
        st.error("Datos de previsualización no están disponibles.")

            


# Función principal para manejar la interfaz de usuario de Streamlit
def run():
    connection = create_server_connection("localhost", "root", "123", "lucmonet")
    
    # Interfaz de usuario de Streamlit para recopilar datos de la factura
    with st.form("invoice_form"):
        st.title("Generador de Facturas")

        from_who = st.text_input("De", "Servicios Lucmo")
        to_who = st.text_input("Cobrar a", "Nombre del cliente")
        date_invoice = st.date_input("Fecha")

        st.subheader("Añadir Servicio")
        servicio = st.text_input("Servicio", "Descripción del servicio")
        cantidad = st.number_input("Cantidad", min_value=1, value=1)
        precio = st.number_input("Precio", min_value=0.0, format='%f')
        
        if st.button("Ver Facturas"):
            facturas = get_facturas(connection)
        if facturas:
            st.subheader("Lista de Facturas")
            for factura in facturas:
                factura_id = factura[0]
                cliente_id = factura[1]
                fecha_factura = factura[4]
                cliente_info = obtener_nombre_cliente_por_id(cliente_id, connection)
                servicios_asignados = servicio_asignados_cliente(cliente_id, connection)
                total = obtener_total_factura(factura_id, connection)
                descuento = Decimal('0.0')  # Asegúrate de que este valor es el correcto

                #  función generar_factura_pdf retorna la ruta completa del archivo PDF
                nombre_archivo_pdf = f"factura-{factura_id}.pdf"
                ruta_archivo_pdf = os.path.join('./facturas_generadas', nombre_archivo_pdf)
                pdf_dir = './facturas_generadas'
                if not os.path.exists(pdf_dir):
                    ruta_archivo_pdf = generar_factura_pdf(cliente_id, servicios_asignados, fecha_factura, total, descuento, connection)

                with st.container():
                    st.write(f"ID: {factura_id} - Cliente: {cliente_info} - Total: ${total}")
                    with open(ruta_archivo_pdf, "rb") as pdf_file:
                        st.download_button(
                            label="Descargar Factura",
                            data=pdf_file,
                            file_name=nombre_archivo_pdf,
                            mime="application/pdf"
                        )
        else:
            st.write("No hay facturas disponibles.")


        st.subheader("Descuentos")
        descuento = Decimal(str(descuento))
        descuento = st.number_input("Descuento %", min_value=0.0, value=0.0, format='%f')

        submit_button = st.form_submit_button("Generar Factura")

        if submit_button:
            cliente = obtener_cliente_por_nombre(to_who, connection)

            if cliente:
                items = [{"Servicio": servicio, "Cantidad": cantidad, "Precio": precio}]
                total = sum(item["Cantidad"] * item["Precio"] for item in items)
                pdf_file = generar_factura_pdf(cliente_id, servicios_asignados, fecha_factura, total, descuento, connection, factura_id)

                mostrar_factura_pdf(pdf_file, servicio_asignados_cliente)
            else:
                st.error("El cliente no existe. Por favor, verifica el nombre.")


if __name__ == "__main__":
    """ Llamada a la función principal"""
    run()