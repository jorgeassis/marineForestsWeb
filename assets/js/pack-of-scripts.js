

$(document).ready(function(){
       $('#loading').fadeOut( 300 );
   });

currentHeight = $('.read-more').outerHeight();

if ( currentHeight > 260) {

$('.read-more').readMore({    readMoreLinkClass: "read-more__link",
                              readMoreText: "Read more",
                              readLessText: "Read less",
                              readMoreHeight: 100
                              });

                            };



$('.datepicker').pickadate({
  selectYears: true,
  selectYears: 300,
  weekdaysShort: ['S', 'M', 'T', 'W', 'T', 'F', 'S'],
  showMonthsShort: true,
  formatSubmit: 'yyyy-mm-dd',
  format: 'yyyy-mm-dd',
  min: new Date(1750,01,01),
  max: new Date()
});



jQuery(document).ready(function($) {
      var alterClass = function() {
      var ww = document.body.clientWidth;
      if (ww < 990) {
      $('.medium-pic').removeClass('wide');
      $('.medium-pic').addClass('narrow');

      $('.barplot').hide();

      $('.variable-margin-top').removeClass('wide');
      $('.variable-margin-top').addClass('narrow');

      $('.queryresults-container').removeClass('wide');
      $('.queryresults-container').addClass('narrow');

      } else if (ww >= 990) {
      $('.medium-pic').removeClass('narrow');
      $('.medium-pic').addClass('wide');

      $('.barplot').show();

      $('.variable-margin-top').removeClass('narrow');
      $('.variable-margin-top').addClass('wide');

      $('.queryresults-container').addClass('wide');
      $('.queryresults-container').removeClass('narrow');

      };
      };
      $(window).resize(function(){
      alterClass();
      });
      //Fire it when the page first loads:
      alterClass();
});
