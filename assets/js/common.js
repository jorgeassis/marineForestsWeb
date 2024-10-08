String.prototype.hashCode = function() {
	var hash = 5381;
	for (var i = 0; i < this.length; i++) {
		hash = ((hash << 5) + hash) + this.charCodeAt(i); /* hash * 33 + c */
	}
	return hash;
};

function layerColour(name, transparency) {
	switch(name) {
	case 'aeroway':
		return "rgba(234,64,128,"+transparency+")";
	case 'boundary':
		return "rgba(192,192,192,"+transparency+")";
	case 'building':
		return "rgba(128,128,0,"+transparency+")";
	case 'contour':
		return "rgba(222,184,135,"+transparency+")";
	case 'graticule':
		return "rgba(0,0,0,"+transparency+")";
	case 'housenumber':
		return "rgba(64,64,0,"+transparency+")";
	case 'land':
		return "rgba(255,255,255,"+transparency+")";
	case 'landcover':
		return "rgba(0,255,0,"+transparency+")";
	case 'landuse':
		return "rgba(128,255,0,"+transparency+")";
	case 'mountain_peak':
		return "rgba(64,64,64,"+transparency+")";
	case 'park':
		return "rgba(0,255,128,"+transparency+")";
	case 'place':
		return "rgba(255,0,0,"+transparency+")";
	case 'poi':
		return "rgba(255,0,128,"+transparency+")";
	case 'transportation':
		return "rgba(64,64,64,"+transparency+")";
	case 'transportation_name':
		return "rgba(32,32,32,"+transparency+")";
	case 'water':
		return "rgba(32,32,255,"+transparency+")";
	case 'water_name':
		return "rgba(0,0,128,"+transparency+")";
	case 'waterway':
		return "rgba(0,0,255,"+transparency+")";
	case 'world_extent':
		return "rgba(200,200,200,"+transparency+")";
	default:
		console.log("Unknown layer", name);
		return "rgba(0,0,0,"+transparency+")";
	}
}

var colours = ['red', 'blue', 'green', 'orange'];

var i = 0;

function createStyle() {
	var point = new ol.style.Style({
		image: new ol.style.Circle({
			fill: new ol.style.Fill({color: '#22bbff'}),
			radius: 5
		}),
		fill: new ol.style.Fill({color: '#22bbff'})
	});

	var fill = new ol.style.Fill({color: ''});
	var stroke = new ol.style.Stroke({color: '', width: 1});
	var polygon = new ol.style.Style({fill: fill});
	var strokedPolygon = new ol.style.Style({fill: fill, stroke: stroke});
	var line = new ol.style.Style({stroke: stroke});

	var text = new ol.style.Style({text: new ol.style.Text({
		text: '', fill: fill, font: '13px "Open Sans", "Arial Unicode MS"'
	})});

	var styles = [];
	return function(feature, resolution) {
		var length = 0;
		var geom = feature.getGeometry()
		var type = feature.getType();
		var layer = feature.get('layer');
		if (type == 'Point') {
			text.getText().setText(feature.get('name'));
			fill.setColor(layerColour(layer, '1.0'));

			if (layer == 'mountain_peak') {
				if (feature.get('rank') == 1) {
					text.getText().setText('▲ ' + feature.get('name') + ' (' + feature.get('ele') + 'm)');
					text.getText().setFont('12px sans-serif');
					styles[length++] = text;
				} else {
					text.getText().setText('▲');
					text.getText().setFont('8px sans-serif');
					styles[length++] = text;
				}
			} else if (layer == 'housenumber') {
				text.getText().setText(feature.get('housenumber'));
				styles[length++] = text;
			} else if (layer == 'place') {
				text.getText().setFont('13px sans-serif');
				styles[length++] = text;
			} else if (layer == 'poi') {
				text.getText().setFont('8px sans-serif');
				if (!feature.get('name')) {
					text.getText().setText(feature.get('class'));
				}
				styles[length++] = text;
			} else if (layer == 'water_name') {
				text.getText().setFont('13px sans-serif');
				styles[length++] = text;
			} else {
				console.log("Unknown point layer", layer, feature);
				text.getText().setFont('13px sans-serif');
				styles[length++] = text;
			}
		}
		else if (type == 'LineString' || type == 'MultiLineString') {
			fill.setColor(layerColour(layer, '0.5'));
			stroke.setColor(layerColour(layer, '0.8'));
			stroke.setWidth(1);
			styles[length++] = line;
		}
		else if (type == 'Polygon') {
			fill.setColor(layerColour(layer, '0.5'));
			stroke.setColor(layerColour(layer, '0.8'));
			stroke.setWidth(0.5);
			styles[length++] = strokedPolygon;
		}
		styles.length = length;
		return styles;
	};
}

var densityColours = ["#b50b0b", "#d85c52", "#e67b74", "#f19995", "#f9b8b6", "#ffd6d6"];
var pointStyles = Array(6).fill().map((_, i) => (
	new ol.style.Style({
		image: new ol.style.Circle({
			fill: new ol.style.Fill({color: densityColours[i]}),
			radius: 1
		}),
		fill: new ol.style.Fill({color: densityColours[i]}),
		stroke: new ol.style.Stroke({color: '#444444'})
	})
));

function createDensityStyle() {
	var styles = [];
	return function(feature, resolution) {
		var length = 0;
		var magnitude = Math.trunc(Math.min(5, Math.floor(Math.log(feature.get('total')))));
		// console.log("Colour ", magnitude, densityColours[magnitude]);
		styles[length++] = pointStyles[magnitude];
		styles.length = length;
		return styles;
	};
}
